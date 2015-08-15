from ast import Lambda
from ctypes import c_int
import ctypes
import ctree
from ctree.c.nodes import FunctionCall, SymbolRef, FunctionDecl, For, Assign, \
    Constant, Lt, PreInc, ArrayRef, Return, CFile
from ctree.cpp.nodes import CppDefine
from ctree.jit import LazySpecializedFunction, ConcreteSpecializedFunction
from ctree.nodes import Project
from ctree.transformations import PyBasicConversions
from ctree.visitors import NodeTransformer
import numpy as np

import logging
logging.basicConfig(level=20)


def np_map(function, array):
    vec_func = np.frompyfunc(function, 1, 1)
    array[:] = vec_func(array)
    return array


def np_reduce(function, array):
    return reduce(function, array.flat)


def np_elementwise(function, array1, array2):
    array1[:] = function(array1, array2)
    return array1


class LambdaLifter(NodeTransformer):
    lambda_counter = 0

    def __init__(self):
        self.lifted_functions = []

    def visit_Lambda(self, node):
        self.generic_visit(node)
        macro_name = "LAMBDA_" + str(self.lambda_counter)
        LambdaLifter.lambda_counter += 1
        node = PyBasicConversions().visit(node)
        node.name = macro_name
        macro = CppDefine(macro_name, node.params, node.defn[0].value)
        self.lifted_functions.append(macro)

        return SymbolRef(macro_name)


class BaseNpFunctionalTransformer(NodeTransformer):
    lifted_functions = []
    func_count = 0

    def __init__(self, array_type):
        self.array_type = array_type

    def visit_Call(self, node):
        self.generic_visit(node)
        if getattr(node.func, "id", None) != self.func_name:
            return node

        return self.convert(node)

    def convert(self, node):
        inner_function = node.args[0]
        if not isinstance(inner_function, Lambda):
            raise Exception(
                self.func_name + " requires lambda to be specialized")

        lambda_lifter = LambdaLifter()
        inner_function = lambda_lifter.visit(inner_function)

        self.lifted_functions.extend(lambda_lifter.lifted_functions)

        func_def = self.get_func_def(inner_function)
        BaseNpFunctionalTransformer.lifted_functions.append(func_def)
        c_node = FunctionCall(SymbolRef(func_def.name), node.args[1:])
        return c_node

    @property
    def gen_func_name(self):
        name = "%s_%s" % (self.func_name, str(type(self).func_count))
        type(self).func_count += 1
        return name

    @property
    def func_name(self):
        raise NotImplementedError("Class %s should override func_name()"
                                  % type(self))

    def get_func_def(self, inner_function_name):
        raise NotImplementedError("Class %s should override get_func_def()"
                                  % type(self))


class NpMapTransformer(BaseNpFunctionalTransformer):
    func_name = "np_map"

    def get_func_def(self, inner_function):
        number_items = np.prod(self.array_type._shape_)
        params = [SymbolRef("A", self.array_type())]
        return_type = self.array_type()
        defn = [
            For(Assign(SymbolRef("i", c_int()), Constant(0)),
                Lt(SymbolRef("i"), Constant(number_items)),
                PreInc(SymbolRef("i")),
                [
                    Assign(ArrayRef(SymbolRef("A"), SymbolRef("i")),
                           FunctionCall(inner_function,
                                        [ArrayRef(SymbolRef("A"),
                                                  SymbolRef("i"))])),
                ]),
            Return(SymbolRef("A")),
        ]
        return FunctionDecl(return_type, self.gen_func_name, params, defn)


class NpReduceTransformer(BaseNpFunctionalTransformer):
    func_name = "np_reduce"

    def get_func_def(self, inner_function):
        number_items = np.prod(self.array_type._shape_)
        params = [SymbolRef("A", self.array_type())]
        elements_type = self.array_type._dtype_.type()
        return_type = elements_type
        defn = [
            Assign(SymbolRef("accumulator", elements_type),
                   ArrayRef(SymbolRef("A"), Constant(0))),
            For(Assign(SymbolRef("i", c_int()), Constant(1)),
                Lt(SymbolRef("i"), Constant(number_items)),
                PreInc(SymbolRef("i")),
                [Assign(
                    SymbolRef("accumulator"),
                    FunctionCall(inner_function, [SymbolRef("accumulator"),
                                                  ArrayRef(SymbolRef("A"),
                                                           SymbolRef("i"))])
                )]
                ),
            Return(SymbolRef("accumulator")),
        ]
        return FunctionDecl(return_type, self.gen_func_name, params, defn)


class NpElementwiseTransformer(BaseNpFunctionalTransformer):
    func_name = "np_elementwise"

    def get_func_def(self, inner_function):
        number_items = np.prod(self.array_type._shape_)
        params = [SymbolRef("A", self.array_type()),
                  SymbolRef("B", self.array_type())]
        return_type = self.array_type()
        defn = [
            For(Assign(SymbolRef("i", c_int()), Constant(0)),
                Lt(SymbolRef("i"), Constant(number_items)),
                PreInc(SymbolRef("i")),
                [
                    Assign(ArrayRef(SymbolRef("A"), SymbolRef("i")),
                           FunctionCall(inner_function,
                                        [ArrayRef(SymbolRef("A"),
                                                  SymbolRef("i")),
                                         ArrayRef(SymbolRef("B"),
                                                  SymbolRef("i"))])),
                ]),
            Return(SymbolRef("A")),
        ]
        return FunctionDecl(return_type, self.gen_func_name, params, defn)


class NpFunctionalTransformer(object):
    transformers = [NpMapTransformer,
                    NpReduceTransformer,
                    NpElementwiseTransformer]

    def __init__(self, array_type):
        self.array_type = array_type

    def visit(self, tree):
        for transformer in self.transformers:
            transformer(self.array_type).visit(tree)
        return tree

    @staticmethod
    def lifted_functions():
        return BaseNpFunctionalTransformer.lifted_functions


def sum_array(a):
    np_map(lambda x: x*2, a)
    np_elementwise(lambda x, y: x+y, a, a)
    return np_reduce(lambda x, y: x+y, np_map(lambda x: x/4, a))


class BasicTranslator(LazySpecializedFunction):

    def args_to_subconfig(self, args):
        arg = args[0]
        arg_type = np.ctypeslib.ndpointer(arg.dtype, arg.ndim, arg.shape)
        return {'arg_type': arg_type}

    def transform(self, tree, program_config):
        arg_type = program_config.args_subconfig['arg_type']
        tree = NpFunctionalTransformer(arg_type).visit(tree)
        tree = PyBasicConversions().visit(tree)

        fn = tree.find(FunctionDecl, name="apply")
        fn.params[0].type = arg_type()
        fn.return_type = arg_type._dtype_.type()

        lifted_functions = NpFunctionalTransformer.lifted_functions()
        c_translator = CFile("generated", [lifted_functions, tree])

        return [c_translator]

    def finalize(self, transform_result, program_config):
        proj = Project(transform_result)

        arg_config, tuner_config = program_config
        arg_type = arg_config['arg_type']
        entry_type = ctypes.CFUNCTYPE(arg_type._dtype_.type, arg_type)

        return BasicFunction("apply", proj, entry_type)


class BasicFunction(ConcreteSpecializedFunction):
    def __init__(self, entry_name, project_node, entry_typesig):
        self._c_function = self._compile(entry_name, project_node, entry_typesig)

    def __call__(self, *args, **kwargs):
        return self._c_function(*args, **kwargs)


if __name__ == '__main__':
    c_sum_array = BasicTranslator.from_function(sum_array)

    test_array = np.array([range(10), range(10, 20)])
    a = sum_array(test_array)
    print a
    b = c_sum_array(test_array)
    print b

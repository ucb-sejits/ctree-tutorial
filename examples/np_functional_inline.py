from ast import Lambda
from ctypes import c_int
import ctypes
import ctree
from ctree.c.nodes import FunctionCall, SymbolRef, FunctionDecl, For, Assign, \
    Constant, Lt, PreInc, ArrayRef, Return, CFile, MultiNode
from ctree.cpp.nodes import CppDefine
from ctree.jit import LazySpecializedFunction, ConcreteSpecializedFunction
from ctree.nodes import Project
from ctree.transformations import PyBasicConversions
from ctree.visitors import NodeTransformer
import numpy as np


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

        params = self._get_params(node)
        defn = self._get_defn(node)

        func_def, return_ref = self.get_def(inner_function, params)

        c_node = MultiNode(defn + lambda_lifter.lifted_functions + func_def)
        setattr(c_node, 'return_ref', return_ref)
        return c_node

    def _get_params(self, node):
        params = map(lambda x: getattr(x, 'return_ref', x), node.args[1:])
        return params

    def _get_defn(self, node):
        defn = []
        for arg in node.args[1:]:
            if isinstance(arg, MultiNode):
                defn.extend(arg.body)
        return defn

    @property
    def func_name(self):
        raise NotImplementedError("Class %s should override func_name()"
                                  % type(self))

    def get_def(self, inner_function_name, params):
        raise NotImplementedError("Class %s should override get_def()"
                                  % type(self))


class NpMapTransformer(BaseNpFunctionalTransformer):
    func_name = "np_map"

    def get_def(self, inner_function, params):
        array_ref = params[0]
        number_items = np.prod(self.array_type._shape_)
        defn = [
            For(Assign(SymbolRef("i", c_int()), Constant(0)),
                Lt(SymbolRef("i"), Constant(number_items)),
                PreInc(SymbolRef("i")),
                [
                    Assign(ArrayRef(array_ref, SymbolRef("i")),
                           FunctionCall(inner_function,
                                        [ArrayRef(array_ref,
                                                  SymbolRef("i"))])),
                ])
        ]
        return defn, array_ref


class NpReduceTransformer(BaseNpFunctionalTransformer):
    func_name = "np_reduce"
    _count = 0

    def get_def(self, inner_function, params):
        array_ref = params[0]
        number_items = np.prod(self.array_type._shape_)
        elements_type = self.array_type._dtype_.type()
        accumulator_ref = "accumulator_%i" % self.count
        defn = [
            Assign(SymbolRef(accumulator_ref, elements_type),
                   ArrayRef(array_ref, Constant(0))),
            For(Assign(SymbolRef("i", c_int()), Constant(1)),
                Lt(SymbolRef("i"), Constant(number_items)),
                PreInc(SymbolRef("i")),
                [Assign(
                    SymbolRef(accumulator_ref),
                    FunctionCall(inner_function, [SymbolRef(accumulator_ref),
                                                  ArrayRef(array_ref,
                                                           SymbolRef("i"))])
                )])
        ]

        return defn, SymbolRef(accumulator_ref)

    @property
    def count(self):
        old_count = NpReduceTransformer._count
        NpReduceTransformer._count += 1
        return old_count


class NpElementwiseTransformer(BaseNpFunctionalTransformer):
    func_name = "np_elementwise"

    def get_def(self, inner_function, params):
        number_items = np.prod(self.array_type._shape_)
        defn = [
            For(Assign(SymbolRef("i", c_int()), Constant(0)),
                Lt(SymbolRef("i"), Constant(number_items)),
                PreInc(SymbolRef("i")),
                [
                    Assign(ArrayRef(params[0], SymbolRef("i")),
                           FunctionCall(inner_function,
                                        [ArrayRef(params[0], SymbolRef("i")),
                                         ArrayRef(params[1], SymbolRef("i"))
                                         ])),
                ])
        ]
        return defn, params[0]


class AssignFixer(NodeTransformer):
    def visit_Assign(self, node):
        self.generic_visit(node)
        return self._get_defn(node)

    def visit_Return(self, node):
        self.generic_visit(node)
        return self._get_defn(node)

    def _get_defn(self, node):
        if not hasattr(node.value, 'return_ref'):
            return node
        defn = node.value
        node.value = defn.return_ref
        return MultiNode([defn, node])


class NpFunctionalTransformer(object):
    transformers = [NpMapTransformer,
                    NpReduceTransformer,
                    NpElementwiseTransformer]

    def __init__(self, array_type):
        self.array_type = array_type

    def visit(self, tree):
        for transformer in self.transformers:
            transformer(self.array_type).visit(tree)
        AssignFixer().visit(tree)
        return tree


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

        c_translator = CFile("generated", [tree])

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
    import logging
    logging.basicConfig(level=20)

    c_sum_array = BasicTranslator.from_function(sum_array)

    test_array = np.array([range(10), range(10, 20)])
    a = sum_array(test_array)
    print a
    test_array = np.array([range(10), range(10, 20)])
    b = c_sum_array(test_array)
    print b

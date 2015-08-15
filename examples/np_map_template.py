from ast import Lambda
import ctypes
import ctree
from ctree.c.nodes import FunctionCall, SymbolRef, FunctionDecl, Constant, \
    CFile
from ctree.cpp.nodes import CppDefine
from ctree.jit import LazySpecializedFunction, ConcreteSpecializedFunction
from ctree.nodes import Project
from ctree.templates.nodes import StringTemplate
from ctree.transformations import PyBasicConversions
from ctree.visitors import NodeTransformer
import numpy as np

import logging
logging.basicConfig(level=20)


def np_map(function, array):
    vec_func = np.frompyfunc(function, 1, 1)
    array[:] = vec_func(array)
    return array


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
        defn = StringTemplate("""\
            for (int i = 0; i < $NUMBER_ITEMS; ++i) {
                A[i] = $INNER_FUNCTION(A[i]);
            }
            return A;
        """, {'NUMBER_ITEMS': Constant(number_items),
              'INNER_FUNCTION': inner_function}
        )
        return FunctionDecl(return_type, self.gen_func_name, params, [defn])


def square_array(a):
    np_map(lambda x: x*2, a)


class BasicTranslator(LazySpecializedFunction):

    def args_to_subconfig(self, args):
        arg = args[0]
        arg_type = np.ctypeslib.ndpointer(arg.dtype, arg.ndim, arg.shape)
        return {'arg_type': arg_type}

    def transform(self, tree, program_config):
        arg_type = program_config.args_subconfig['arg_type']
        tree = NpMapTransformer(arg_type).visit(tree)
        tree = PyBasicConversions().visit(tree)

        fn = tree.find(FunctionDecl, name="apply")
        fn.params[0].type = arg_type()

        lifted_functions = NpMapTransformer.lifted_functions
        c_translator = CFile("generated", [lifted_functions, tree])

        return [c_translator]

    def finalize(self, transform_result, program_config):
        proj = Project(transform_result)

        arg_config, tuner_config = program_config
        arg_type = arg_config['arg_type']
        entry_type = ctypes.CFUNCTYPE(None, arg_type)

        return BasicFunction("apply", proj, entry_type)


class BasicFunction(ConcreteSpecializedFunction):
    def __init__(self, entry_name, project_node, entry_typesig):
        self._c_function = self._compile(entry_name, project_node, entry_typesig)

    def __call__(self, *args, **kwargs):
        return self._c_function(*args, **kwargs)


if __name__ == '__main__':
    c_square_array = BasicTranslator.from_function(square_array)

    test_array = np.array([range(10), range(10, 20)])
    square_array(test_array)
    print test_array
    c_square_array(test_array)
    print test_array

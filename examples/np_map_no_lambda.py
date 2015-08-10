from ctypes import c_int
import ctypes
from ctree.jit import LazySpecializedFunction, ConcreteSpecializedFunction
from ctree.nodes import Project
from ctree.transformations import PyBasicConversions
import numpy as np
from ctree.c.nodes import FunctionCall, SymbolRef, FunctionDecl, For, Assign, \
        Constant, Lt, PreInc, ArrayRef, Return, CFile
from ctree.visitors import NodeTransformer

import logging
logging.basicConfig(level=20)


def np_map(function, array):
    vec_func = np.vectorize(function)
    array[:] = vec_func(array)
    return array


def square_array(a):
    np_map(lambda x: x*x, a)


class NpMapTransformer(NodeTransformer):
    func_name = "np_map"
    lifted_functions = []

    def __init__(self, array_type):
        self.array_type = array_type

    def visit_Call(self, node):
        self.generic_visit(node)
        # return unmodified node if function being called is not np_map
        if getattr(node.func, "id", None) != self.func_name:
            return node

        return self.convert(node) # do the required transformations, we
                                  # still have to implement this method

    def get_func_def(self, inner_function):
        number_items = np.prod(self.array_type._shape_) # get number of items in the array

        params = [SymbolRef("A", self.array_type())] # this is the C function parameter,
                                                     # observe we only have the array now.
                                                     # The lambda function will not be a
                                                     # parameter anymore, instead it will
                                                     # be part of the function definition.
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
        return FunctionDecl(return_type, self.func_name, params, defn)

    def convert(self, node):
        inner_function = node.args[0]
        func_def = self.get_func_def(inner_function)
        NpMapTransformer.lifted_functions.append(func_def)

        # this the node that will substitute the old one, a function call to
        # our new generated function without the first argument (the lambda)
        c_node = FunctionCall(SymbolRef(func_def.name), node.args[1:])
        return c_node


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


c_square = BasicTranslator.from_function(square_array)

test_array = np.array([range(10), range(10, 20)])
square_array(test_array)
print test_array
c_square(test_array)
print test_array

import ctypes
from ctree.types import get_ctype
from ctree.nodes import Project
from ctree.c.nodes import FunctionDecl, CFile
from ctree.transformations import PyBasicConversions
from ctree.jit import LazySpecializedFunction
from ctree.jit import ConcreteSpecializedFunction

import timeit


def fib(n):
    if n < 2:
        return n
    else:
        return fib(n - 1) + fib(n - 2)


class BasicTranslator(LazySpecializedFunction):

    def args_to_subconfig(self, args):
        return {'arg_type': type(get_ctype(args[0]))}

    def transform(self, tree, program_config):
        tree = PyBasicConversions().visit(tree)

        fib_fn = tree.find(FunctionDecl, name="apply")
        arg_type = program_config.args_subconfig['arg_type']
        fib_fn.return_type = arg_type()
        fib_fn.params[0].type = arg_type()
        c_translator = CFile("generated", [tree])

        return [c_translator]

    def finalize(self, transform_result, program_config):
        proj = Project(transform_result)

        arg_config, tuner_config = program_config
        arg_type = arg_config['arg_type']
        entry_type = ctypes.CFUNCTYPE(arg_type, arg_type)

        return BasicFunction("apply", proj, entry_type)


class BasicFunction(ConcreteSpecializedFunction):
    def __init__(self, entry_name, project_node, entry_typesig):
        self._c_function = self._compile(entry_name, project_node,
                                         entry_typesig)

    def __call__(self, *args, **kwargs):
        return self._c_function(*args, **kwargs)

c_fib = BasicTranslator.from_function(fib)

print timeit.repeat('c_fib(40)', 'from __main__ import c_fib', repeat=20,
                    number=1)

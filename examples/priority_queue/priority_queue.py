from ctypes import Structure, POINTER
import ctypes
import heapq
import os
import ctree
from ctree.c.nodes import FunctionDecl, SymbolRef, BinaryOp, Op, Return, \
    FunctionCall
from ctree.c.nodes import CFile
from ctree.jit import LazySpecializedFunction, ConcreteSpecializedFunction
from ctree.nodes import Project
from ctree.templates.nodes import StringTemplate
from ctree.transformations import PyBasicConversions
import numpy as np


from examples.np_functional_inline import np_map, NpFunctionalTransformer

import logging
# logging.basicConfig(level=20)


class PriorityQueue(object):
    def __init__(self, max_size=None):
        self.heap = []
        self.max_size = max_size

    @property
    def size(self):
        return len(self.heap)

    def push(self, new_element):
        if self.max_size is None or self.size < self.max_size:
            heapq.heappush(self.heap, new_element)

    def pop(self):
        return heapq.heappop(self.heap)

    def codegen(self):
        return "struct " + type(self).__name__ + "*"

    def __str__(self):
        return self.codegen()


def priority_queue(max_size):
    return PriorityQueue(max_size)


def priority_queue_push(heap, new_element):
    heap.push(new_element)
    return new_element


def priority_queue_pop(heap):
    return heap.pop()


from ctree.types import register_type_codegenerators

register_type_codegenerators({
    PriorityQueue: lambda t: "struct " + type(t).__name__ + "*"})


class BasicTranslator(LazySpecializedFunction):

    def args_to_subconfig(self, args):
        arg = args[0]
        arg_type = np.ctypeslib.ndpointer(arg.dtype, arg.ndim, arg.shape)
        return {'arg_type': arg_type}

    def transform(self, tree, program_config):
        arg_type = program_config.args_subconfig['arg_type']
        tree = NpFunctionalTransformer(arg_type).visit(tree)
        tree = PyBasicConversions().visit(tree)

        priority_queue_path = os.path.dirname(os.path.abspath(__file__))
        pq_header = os.path.join(priority_queue_path, "priority_queue.h")
        pq_c = os.path.join(priority_queue_path, "priority_queue.c")
        ctree.CONFIG.set('c', 'LDFLAGS', pq_c)
        includes = [StringTemplate("""\
            #include <stdio.h>
            #include "%s" """ % pq_header)]
        func_def = [FunctionDecl(
            return_type=PriorityQueue(),
            name="priority_queue",
            params=[SymbolRef("heap_size", ctypes.c_int())],
            defn=[Return(FunctionCall(SymbolRef("new_priority_queue"),
                                      [SymbolRef("heap_size")]))]
        )]

        fib_fn = tree.find(FunctionDecl, name="apply")
        fib_fn.params[0].type = arg_type()
        c_translator = CFile("generated", includes + func_def + [tree])

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


def heap_sort(array):
    pq = priority_queue(20)
    np_map(lambda x: priority_queue_push(pq, x), array)
    np_map(lambda _: priority_queue_pop(pq), array)


if __name__ == '__main__':
    c_heap_sort = BasicTranslator.from_function(heap_sort)

    test_python_array = np.array([7, 3, 8, 5, 4, 9, 12, 4, 1])
    test_c_array = test_python_array.copy()

    heap_sort(test_python_array)
    c_heap_sort(test_c_array)

    print test_python_array, test_c_array

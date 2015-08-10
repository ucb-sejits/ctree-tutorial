import ctree
from ctree.visitors import NodeVisitor, NodeTransformer


class StringCounter(NodeVisitor):
    def __init__(self):
        self.number_strings = 0

    def visit_Str(self, node):
        self.number_strings += 1


class StringPrinter(NodeVisitor):
    def visit_Str(self, node):
        print node.s


class UppercaseConverter(NodeTransformer):
    def visit_Str(self, node):
        node.s = node.s.upper()
        return node


def some_strings():
    a = "first string"
    b = "second string"
    c = "third string"
    return a + b + c


ast = ctree.get_ast(some_strings)
sc = StringCounter()
sc.visit(ast)

StringPrinter().visit(ast)

print sc.number_strings

UppercaseConverter().visit(ast)
StringPrinter().visit(ast)
ctree.ipython_show_ast(ast)

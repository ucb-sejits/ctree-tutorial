=========================
Visitors and Transformers
=========================

Creating Visitors and Transformers
----------------------------------
In order to retrieve information or modify the AST we need to use Visitors and
Transformers. A Visitor traverses the AST looking for nodes with types you
specified, consider the following example:

.. code:: python

    from ctree.visitors import NodeVisitor

    class StringPrinter(NodeVisitor):
        def visit_Str(self, node):
            print node.s

This is a visitor that traverses a tree and print every string it founds. Every
method in the visitor following the name convention ``visit_Type`` is
automatically called when the ``Type`` is found in the tree. This visitor has a
method ``visit_Str`` so every time a node with the type ``Str`` is found, this
method is called with such node as argument. The code below uses this visitor.

.. code:: python

    from ctree import get_ast

    def some_strings():
        a = "first string"
        b = "second string"
        c = "third string"
        return 0

    ast = get_ast(some_strings)
    StringPrinter().visit(ast)

The output should be::

    first string
    second string
    third string

Using ``get_ast`` we got the AST from the function and used the visitor the
same way we used the ``PyBasicConversions`` in the specializer.

.. note::
     We didn't have to call ``get_ast`` in the specializer as the ``tree``
     argument, from the transform_ method, was already converted to AST.

We can also do something similar in order to count the number of strings in the
AST.

.. code:: python

    class StringCounter(NodeVisitor):
        def __init__(self):
            self.number_strings = 0

        def visit_Str(self, node):
            self.number_strings += 1

    sc = StringCounter()
    sc.visit(ast)
    print sc.number_strings

Transformers are really similar to Visitors, but they have the ability to
modify the nodes they are visiting.

.. code:: python

    from ctree.visitors import NodeTransformer

    class UppercaseConverter(NodeTransformer):
        def visit_Str(self, node):
            node.s = node.s.upper()
            return node

    UppercaseConverter().visit(ast)
    StringPrinter().visit(ast)

The output should be::

    FIRST STRING
    SECOND STRING
    THIRD STRING

Observe that now the method returns a modified node. The new node will
substitute the old one in the AST. When we use the ``StringPrinter`` again
it's possible to see that the strings are now uppercase. This example can be
found at `<examples/simple_visit_transform.py>`_

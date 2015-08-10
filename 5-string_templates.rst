================
String Templates
================

Instead of writing code using ctree nodes as we did in the previous section,
sometimes it's more convenient to write the actual C code. We can do this in
ctree using String Templates.

String Templates allow you to put some C code in a string and insert it in the
middle of the tree. The following example is an alternative implementation of
``NpMapTransformer`` using ``StringTemplate``:

.. code:: python

    from ctree.templates.nodes import StringTemplate

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

The ``StringTemplate`` node may have two arguments: The first is the string
with C code; The second is a dictionary with ctree nodes that will be used to
replace eventual tags in the string. Observe how we replaced ``'NUMBER_ITEMS'``
and ``'INNER_FUNCTION'`` with appropriate ctree nodes.

This method improves readability but decreases robustness. Subsequent
transformers will not be able to modify the string template as they would be
able to modify regular ctree nodes. For this example, either methods can be
applied as other subsequent transformers will not need to modify this
structure.

The complete example can be found at `<examples/np_map_template.py>`_

You don't always have to use the C code as a string in your python code. If you
have a big C code you want to use, it may be better to use a file to hold your
string template. If that is the case, you just have to use the ``FileTemplate``
class. Its usage is very similar to the ``StringTemplate`` class but instead of
using the string template as first argument, you use the file path.

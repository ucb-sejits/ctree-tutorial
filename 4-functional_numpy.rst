============================
Case Study: Functional Numpy
============================

Introduction
------------
Let's create a specializer to apply ``map``, ``reduce`` and ``elementwise`` in
numpy arrays. ``map`` and ``reduce`` are equivalent to the existing python
built-in functions. ``elementwise`` is a function to make simple element-wise
operations on two numpy arrays.

The first concern when porting those functions to C is that they require a
function as parameter. We could use C function pointers for that but this would
be overcomplicated. Another problem is allocation, to simplify, in the ``map``
function, we will modify the same array so we don't need to allocate a new one.
Similarly, in the ``elementwise`` function we will modify the first array.

The Python Implementations
--------------------------
First let's implement those functions in python, they should be very
straightforward. To differ from existing python functions we will use ``np_``
in front of the name. Here is the ``np_map``:

.. code:: python

    import numpy as np

    def np_map(function, array):
        vec_func = np.vectorize(function)
        array[:] = vec_func(array)
        return array

We're making sure the original array is also being modified, so that we have
the same behavior we will have in C.

The ``np_reduce`` should be exactly the same as the existing python version,
using the flat version of the array:

.. code:: python

    def np_reduce(function, array):
        return reduce(function, array.flat)

This is possible because ``reduce`` returns a single number and requires an
iterator. Numpy arrays also work as an iterator. For multidimensional numpy
arrays, the flat version of the numpy array makes sure we're iterating over the
elements and not sub-arrays.

The ``np_elementwise`` will have the same constrains as ``np_map``:

.. code:: python

    def np_elementwise(function, array1, array2):
        array1[:] = function(array1, array2)
        return array1

Specializing
------------
Time to specialize, as you can tell, those functions don't have an obvious C
equivalent. We will try to specialize a simple function that uses one of those
functions we created:

.. code:: python

    def square_array(a):
        np_map(lambda x: x*x, a)

This is what happens if we use the same specializer we used for the ``fib``
function on this one::

    INFO:ctree.c.nodes:generated C program: (((
    // <file: generated.c>

    long** apply(long** a) {
        np_map(void default(x) {
        return x * x;
    }, a);
    };

    )))
    INFO:ctree.c.nodes:compilation command: gcc -shared -fPIC -O2 -std=c99 -o /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmp1ONImB/square_array/384529141981481102/-7985492147856592190/BasicTranslator/default/generated.so /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmp1ONImB/square_array/384529141981481102/-7985492147856592190/BasicTranslator/default/generated.c
    /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmp1ONImB/square_array/384529141981481102/-7985492147856592190/BasicTranslator/default/generated.c:4:5: warning: implicit declaration of function 'np_map' is invalid in C99 [-Wimplicit-function-declaration]
        np_map(void default(x) {
        ^
    /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmp1ONImB/square_array/384529141981481102/-7985492147856592190/BasicTranslator/default/generated.c:4:12: error: expected expression
        np_map(void default(x) {
               ^
    1 warning and 1 error generated.


The generated code is really wrong. The first problem is that ctree doesn't
have access to the ``np_map`` implementation. But even if it had, it wouldn't
help because the code is very different from C. What we will do is create some
transformers that will modify the AST to something compilable to C. Let's take
care of the ``np_map`` first and than we generalize to the other functions.

We want to intercept calls to ``np_map`` and make them call our C version of
``np_map``. The transformer should have a structure like this:

.. code:: python

    from ctree.visitors import NodeTransformer

    class NpMapTransformer(NodeTransformer):
        func_name = "np_map"

        def __init__(self, array_type):
            self.array_type = array_type

        def visit_Call(self, node):
            self.generic_visit(node)
            # return unmodified node if function being called is not np_map
            if getattr(node.func, "id", None) != self.func_name:
                return node

            return self.convert(node) # do the required transformations, we
                                      # still have to implement this method


This transformer modify every function call to ``np_map`` it finds. We will
make it call our C function instead of the np_map, but the C function it calls
should be generated using the lambda function we're getting as argument. The
type of the array we are using, which includes size, dimensions and elements
type, is being defined at the constructor.

The C function we generate will not be defined in the same place we're calling
it, it must be defined before the function we are in. It's not possible to do
this while traversing the tree. A solution is to create a list that holds every
function that should be "lifted" so that we can generate a C function and
append it to this list. We call this list ``lifted_functions`` and will use it
after the transformer finishes its visit.

Let's create a method to generate this C function. We will define the entire
function using ctree nodes, check the `documentation
<http://ucb-sejits.github.io/ctree-docs/ctree.c.html#module-ctree.c.nodes>`_
for more details on each type of node:

.. code:: python

    from ctypes import c_int
    from ctree.c.nodes import FunctionCall, SymbolRef, FunctionDecl, For, Assign, \
        Constant, Lt, PreInc, ArrayRef, Return, CFile

    class NpMapTransformer(NodeTransformer):
        func_name = "np_map"
        lifted_functions = []

        [...] # __init__ and visit_Call

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

This is a ctree nodes implementation of a map function, the for loop iterates
over every element on the array and applies the ``inner_function``. In fact
there is a problem with using ``FunctionCall`` to call the inner function as
``inner_function`` is actually a ``Lambda`` node and not the name of a
function. We will come back to solve this problem soon.

Finally we implement the ``convert`` method we had called in the ``visit_Call``
method. It will append the new function definition to the ``lifted_functions``
list and will return the function call we will use in place of the old
``Call`` node.

.. code:: python

        def convert(self, node):
            inner_function = node.args[0]
            func_def = self.get_func_def(inner_function)
            NpMapTransformer.lifted_functions.append(func_def)

            # this is the node that will substitute the old Call node, a function call to
            # our new generated function without the first argument (the lambda)
            c_node = FunctionCall(SymbolRef(func_def.name), node.args[1:])
            return c_node

Observe that, even though the node we are visiting is of type ``Call``, we are
returning a node of type ``FunctionCall``. The difference between the two is
that ``Call`` is an ``ast`` node while ``FunctionCall`` is a ``ctree`` node.
``ast`` nodes are defined in the Python `ast module
<https://docs.python.org/2/library/ast.html>`_ and are equivalent to **Python**
expressions. In the other hand, ``ctree`` nodes are equivalent to **C**
expressions. What the ``PyBasicConversions`` transformer does is try to convert
the nodes in the tree from ``ast`` to ``ctree`` node.

Some modifications will also have to be made to the
``LazySpecializedFunction``. Our old ``args_to_subconfig`` from the Fibonacci
Specializer assumed a simple argument, like int or float. Now our argument is
an array. This is how the ``args_to_subconfig`` method from the class inherited
from ``LazySpecializedFunction`` should look like.

.. code:: python

    def args_to_subconfig(self, args):
        arg = args[0]
        arg_type = np.ctypeslib.ndpointer(arg.dtype, arg.ndim, arg.shape)
        return {'arg_type': arg_type}

This assumes a single array as argument. Note that, since the array type
consists of elements type, number of dimensions and shape, any array with a
different shape or element type, will trigger new specializations.

The ``transform`` method also needs some modifications. We need to call the
transformer we created and we don't need to define a return type anymore since
the function we're specializing has no return.

.. code:: python

    def transform(self, tree, program_config):
        # we need the arg_type for the NpMapTransformer
        arg_type = program_config.args_subconfig['arg_type']

        # using the NpMapTransformer, very similar to the PyBasicConversions
        # transformer but here the constructor has an argument
        tree = NpMapTransformer(arg_type).visit(tree)

        tree = PyBasicConversions().visit(tree)

        fn = tree.find(FunctionDecl, name="apply")
        fn.params[0].type = arg_type()

        # getting the lifted_functions list from NpMapTransformer
        lifted_functions = NpMapTransformer.lifted_functions

        # using the lifted_functions and the tree to create the CFile
        c_translator = CFile("generated", [lifted_functions, tree])

        return [c_translator]

We also have to remove the return from the entry type in the finalize method:

.. code:: python

    def finalize(self, transform_result, program_config):
        proj = Project(transform_result)

        arg_config, tuner_config = program_config
        arg_type = arg_config['arg_type']
        entry_type = ctypes.CFUNCTYPE(None, arg_type) # Using None as return type

        return BasicFunction("apply", proj, entry_type)

You can find the complete code up to this point at
`<examples/np_map_no_lambda.py>`_

But if we run it, we get::

    INFO:ctree.c.nodes:generated C program: (((
    // <file: generated.c>
    long* np_map(long* A) {
        for (int i = 0; i < 20; ++ i) {
            A[i] = <_ast.Lambda object at 0x11093ab90>(A[i]);
        };
        return A;
    };

    void apply(long* a) {
        np_map(a);
    };

    )))
    INFO:ctree.c.nodes:compilation command: gcc -shared -fPIC -O2 -std=c99 -o /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpgzPua7/square_array/-6982124631467140425/-7985492147856592190/BasicTranslator/default/generated.so /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpgzPua7/square_array/-6982124631467140425/-7985492147856592190/BasicTranslator/default/generated.c
    /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpgzPua7/square_array/-6982124631467140425/-7985492147856592190/BasicTranslator/default/generated.c:4:16: error: expected expression
            A[i] = <_ast.Lambda object at 0x11093ab90>(A[i]);
                   ^
    /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpgzPua7/square_array/-6982124631467140425/-7985492147856592190/BasicTranslator/default/generated.c:4:17: error: use of undeclared identifier '_ast'
            A[i] = <_ast.Lambda object at 0x11093ab90>(A[i]);
                    ^
    2 errors generated.


As we saw before, the ``inner_function`` we were calling when implementing the
C version of ``np_map`` is actually a ``Lambda`` node. We have to convert the
``Lambda`` node to something equivalent in C. The way we will deal with this
problem is to convert the lambda to a macro function. This can be done with a
simple transformer:

.. code:: python

    from ctree.cpp.nodes import CppDefine

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

This transformer looks for ``Lambda`` nodes, creates an equivalent C macro
function with a unique name, puts this macro definition in the lifted_functions
list and substitutes the ``Lambda`` node by a ``SymbolRef`` to the new macro.

Now we can modify the ``convert`` method from the ``NpMapTransformer`` so that
it applies the LambdaLifter transformer to the ``inner_function`` before using
it:

.. code:: python

    from ast import Lambda

    def convert(self, node):
        inner_function = node.args[0]
        # check if the inner_function is actually a Lambda node, we will only support lambda here
        if not isinstance(inner_function, Lambda):
            raise Exception("np_map requires lambda to be specialized")

        # applying the LambdaLifter to the inner_function, this time we have to
        # save the object in a variable so that we can retrieve the lifted_functions
        # list after
        lambda_lifter = LambdaLifter()
        inner_function = lambda_lifter.visit(inner_function)
        self.lifted_functions.extend(lambda_lifter.lifted_functions)

        func_def = self.get_func_def(inner_function)
        NpMapTransformer.lifted_functions.append(func_def)

        # this is the node that will substitute the old one, a function call to
        # our new generated function without the first argument (the lambda)
        c_node = FunctionCall(SymbolRef(func_def.name), node.args[1:])
        return c_node

You can find the complete code up to this point at `<examples/np_map.py>`_.
When we run the code it works as expected::

    INFO:ctree.jit:detected specialized function call with arg types: [<type 'numpy.ndarray'>]
    INFO:ctree.jit:tuner subconfig: None
    INFO:ctree.jit:arguments subconfig: {'arg_type': <class 'numpy.ctypeslib.ndpointer_<i8_2d_2x10'>}
    INFO:ctree.jit:specialized function cache miss.
    [[  0   1   4   9  16  25  36  49  64  81]
     [100 121 144 169 196 225 256 289 324 361]]
    INFO:ctree.jit:Hash miss. Running Transform
    INFO:ctree.c.nodes:file for generated C: /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpCmMvPf/square_array/-6982124631467140425/-7985492147856592190/BasicTranslator/default/generated.c
    INFO:ctree.c.nodes:generated C program: (((
    // <file: generated.c>
    #define LAMBDA_0(x) (x * x)
    long* np_map(long* A) {
        for (int i = 0; i < 20; ++ i) {
            A[i] = LAMBDA_0(A[i]);
        };
        return A;
    };

    void apply(long* a) {
        np_map(a);
    };

    )))
    INFO:ctree.c.nodes:compilation command: gcc -shared -fPIC -O2 -std=c99 -o /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpCmMvPf/square_array/-6982124631467140425/-7985492147856592190/BasicTranslator/default/generated.so /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpCmMvPf/square_array/-6982124631467140425/-7985492147856592190/BasicTranslator/default/generated.c
    INFO:ctree:execution statistics: (((
      specialized function call: 1
      Filesystem cache miss: 1
      specialized function cache miss: 1
      recognized that caching is disabled: 1
    )))
    [[     0      1     16     81    256    625   1296   2401   4096   6561]
     [ 10000  14641  20736  28561  38416  50625  65536  83521 104976 130321]]

.. note::
    Even though we had a multi dimension numpy array, we use it as a single
    dimension array in our C code.

Now it's time to make our code work with the other functions as well. Most of
the methods we used to create the ``NpMapTransformer`` can be used for the
other functions. We will create a base class with those methods:

.. code:: python

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

Observe this new base class also implements a new method ``gen_func_name`` that
creates unique names to the generated c functions. The new ``NpMapTransformer``
will be much simpler:

.. code:: python

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

We removed the methods that were moved to the base class and we are now using
``self.gen_func_name`` as the name for the C function so that we can use
``np_map`` more than once with different names for each C implementation.

To create a transformation for the ``np_reduce`` we will subclass
``BaseNpFunctionalTransformer`` just like we did for the ``np_map``:

.. code:: python

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

Once again, we just need to override the ``func_name`` and the
``get_func_def`` method. We return a ``FunctionDecl`` implemented using ctree
nodes.

Same thing for the ``np_elementwise``:

.. code:: python

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

Now there are three transformers we have to use in the
``LazySpecializedFunction``. To make our transformers easy to use, we will
create a class that seems like a transformer but actually applies the three
transformers to the tree:

.. code:: python

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

With this class, instead of having to use ``NpMapTransformer``,
``NpReduceTransformer`` and ``NpElementwiseTransformer`` we can just use
``NpFunctionalTransformer``.

To test our new transformers we will specialize the following function:

.. code:: python

    def sum_array(a):
        np_map(lambda x: x*2, a)
        np_elementwise(lambda x, y: x+y, a, a)
        return np_reduce(lambda x, y: x+y, np_map(lambda x: x/4, a))

This is a very weird way to sum all the array elements, but will be good for
our test. We just have to adapt our BasicTranslator to use the
``NpFunctionalTransformer`` and to handle the function return. The complete
code with all the functions and the specializer can be found at
`<examples/np_functional.py>`_

Executing the example we have::

    INFO:ctree.jit:detected specialized function call with arg types: [<type 'numpy.ndarray'>]
    190
    INFO:ctree.jit:tuner subconfig: None
    INFO:ctree.jit:arguments subconfig: {'arg_type': <class 'numpy.ctypeslib.ndpointer_<i8_2d_2x10'>}
    INFO:ctree.jit:specialized function cache miss.
    INFO:ctree.jit:Hash miss. Running Transform
    INFO:ctree.c.nodes:file for generated C: /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmp8h2zGa/sum_array/-6982124631467140425/-7985492147856592190/BasicTranslator/default/generated.c
    INFO:ctree.c.nodes:generated C program: (((
    // <file: generated.c>
    #define LAMBDA_0(x) (x * 2)
    long* np_map_0(long* A) {
        for (int i = 0; i < 20; ++ i) {
            A[i] = LAMBDA_0(A[i]);
        };
        return A;
    };
    #define LAMBDA_1(x) (x / 4)
    long* np_map_1(long* A) {
        for (int i = 0; i < 20; ++ i) {
            A[i] = LAMBDA_1(A[i]);
        };
        return A;
    };
    #define LAMBDA_2(x, y) (x + y)
    long np_reduce_0(long* A) {
        long accumulator = A[0];
        for (int i = 1; i < 20; ++ i) {
            accumulator = LAMBDA_2(accumulator, A[i]);
        };
        return accumulator;
    };
    #define LAMBDA_3(x, y) (x + y)
    long* np_elementwise_0(long* A, long* B) {
        for (int i = 0; i < 20; ++ i) {
            A[i] = LAMBDA_3(A[i], B[i]);
        };
        return A;
    };

    long apply(long* a) {
        np_map_0(a);
        np_elementwise_0(a, a);
        return np_reduce_0(np_map_1(a));
    };

    )))
    INFO:ctree.c.nodes:compilation command: gcc -shared -fPIC -O2 -std=c99 -g -o /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmp8h2zGa/sum_array/-6982124631467140425/-7985492147856592190/BasicTranslator/default/generated.so /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmp8h2zGa/sum_array/-6982124631467140425/-7985492147856592190/BasicTranslator/default/generated.c
    INFO:ctree:execution statistics: (((
      specialized function call: 1
      Filesystem cache miss: 1
      specialized function cache miss: 1
      recognized that caching is disabled: 1
    )))
    190

Observe the functions generated by the specializer. Each use of ``np_map``,
``np_reduce`` or ``np_elementwise`` will generate a new function that uses a
different lambda. Those different lambdas are represented by different macro
functions in C.

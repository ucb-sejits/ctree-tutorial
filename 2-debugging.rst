======================
Debugging Specializers
======================

Introduction
------------
Here we suggest some debugging techniques that may help you develop your
specializers. You will see brief examples of common problems you may face and
possible ways to handle them.

Logging
-------
The first thing you may want to consider, in order to have more information
about what is going on, is to activate logging. This is simply achieved by
adding the following lines to the beginning of the file:

.. code:: python

    import logging
    logging.basicConfig(level=logging.DEBUG)

Among other information, this will show you if ctree is using a cached version
of your generated code or creating a new one. If creating a new one the log
will also show the generated C code.

Let's go back to our Fibonacci specializer. This is what will appear if we
enable logging::

    INFO:ctree.jit:detected specialized function call with arg types: [<type 'int'>]
    INFO:ctree.jit:tuner subconfig: None
    INFO:ctree.jit:arguments subconfig: {'arg_type': <class 'ctypes.c_long'>}
    INFO:ctree.jit:specialized function cache miss.
    INFO:ctree.jit:Hash miss. Running Transform
    INFO:ctree.c.nodes:file for generated C: /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmptwc1Hu/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.c
    INFO:ctree.c.nodes:generated C program: (((
    // <file: generated.c>

    long apply(long n) {
        if (n < 2) {
            return n;
        } else {
            return apply(n - 1) + apply(n - 2);
        };
    };

    )))
    INFO:ctree.c.nodes:compilation command: gcc -shared -fPIC -O2 -std=c99 -o /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmptwc1Hu/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.so /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmptwc1Hu/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.c
    55 55

This shows ctree detected the argument type as an **int** and couldn't find a
cached function to such type. After, it shows the path to the generated C file
and the actual source code in it. The last information it shows is the
compilation command used. If we continue through the log we will see the
following lines::

    INFO:ctree.jit:detected specialized function call with arg types: [<type 'float'>]
    INFO:ctree.jit:tuner subconfig: None
    INFO:ctree.jit:arguments subconfig: {'arg_type': <class 'ctypes.c_double'>}
    INFO:ctree.jit:specialized function cache miss.
    INFO:ctree.jit:Hash miss. Running Transform
    INFO:ctree.c.nodes:file for generated C: /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmptwc1Hu/fib/4268650778531830270/-7985492147856592190/BasicTranslator/default/generated.c
    INFO:ctree.c.nodes:generated C program: (((
    // <file: generated.c>

    double apply(double n) {
        if (n < 2) {
            return n;
        } else {
            return apply(n - 1) + apply(n - 2);
        };
    };

    )))
    INFO:ctree.c.nodes:compilation command: gcc -shared -fPIC -O2 -std=c99 -o /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmptwc1Hu/fib/4268650778531830270/-7985492147856592190/BasicTranslator/default/generated.so /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmptwc1Hu/fib/4268650778531830270/-7985492147856592190/BasicTranslator/default/generated.c
    5.5 5.5

Those lines are pretty similar to the previous ones but now the type detected
is a **float**. Again there's no cached function for this type and ctree
generates another function, now with double as parameter and return type.

In the end you will also be able to see some statistics::

    INFO:ctree:execution statistics: (((
      specialized function call: 2
      Filesystem cache miss: 2
      specialized function cache miss: 2
      recognized that caching is disabled: 1
    )))



No problems occurred yet, we are using the log just to see how everything works
well. Let me introduce some bugs...

Cache Misuse
............
What if, in the ``args_to_subconfig`` method, we messed up and forgot to add
the argument type to the dictionary we are returning:

.. code:: python

    def args_to_subconfig(self, args):
        # return {'arg_type': type(get_ctype(args[0]))}
        return {'arg_type': type(get_ctype(0))}

This way, ``arg_type`` will always be an **int** no matter what the actual.
arguments are. The log will now look like this::

    INFO:ctree.jit:detected specialized function call with arg types: [<type 'int'>]
    INFO:ctree.jit:tuner subconfig: None
    INFO:ctree.jit:arguments subconfig: {'arg_type': <class 'ctypes.c_long'>}
    INFO:ctree.jit:specialized function cache miss.
    INFO:ctree.jit:Hash miss. Running Transform
    INFO:ctree.c.nodes:file for generated C: /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpd9KGMd/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.c
    INFO:ctree.c.nodes:generated C program: (((
    // <file: generated.c>

    long apply(long n) {
        if (n < 2) {
            return n;
        } else {
            return apply(n - 1) + apply(n - 2);
        };
    };

    )))
    INFO:ctree.c.nodes:compilation command: gcc -shared -fPIC -O2 -std=c99 -o /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpd9KGMd/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.so /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpd9KGMd/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.c
    55 55

Everything goes fine when calling the function with integers since this is the
type we are always using. But when we call the function with a float::

    INFO:ctree.jit:detected specialized function call with arg types: [<type 'float'>]
    INFO:ctree.jit:tuner subconfig: None
    INFO:ctree.jit:arguments subconfig: {'arg_type': <class 'ctypes.c_long'>}
    INFO:ctree.jit:specialized function cache miss.
    INFO:ctree.jit:Hash hit. Skipping transform
    Traceback (most recent call last):
      File "fibonacci_specializer_logging.py", line 57, in <module>
        print c_fib(4.5), fib(4.5)
      File "/Library/Python/2.7/site-packages/ctree-0.1.9-py2.7.egg/ctree/jit.py", line 330, in __call__
        return csf(*args, **kwargs)
      File "fibonacci_specializer_logging.py", line 52, in __call__
        return self._c_function(*args, **kwargs)
    ctypes.ArgumentError: argument 1: <type 'exceptions.TypeError'>: wrong type

Observe we have a "``Hash hit. Skipping transform``", this happens because
``args_to_subconfig`` returns exactly the same thing as before. This way the
cached function compiled to **int** is used, causing the
``ctypes.ArgumentError`` exception we see. We are using a **float** argument to
a function that requires **int**. Inspecting the log we can easily detect the
problem.

Defective C Code (Not Compilable)
.................................
Another type of problem that the log helps to spot is when we end up with a
defective C code. A defective C code can be either a code that doesn't compile
or compiles into something that doesn't do what we want. Let's suppose we
forgot to set the return type of the function, this way ctree will set the
return to void:

.. code:: python

    def transform(self, tree, program_config):
        tree = PyBasicConversions().visit(tree)

        fib_fn = tree.find(FunctionDecl, name="apply")
        arg_type = program_config.args_subconfig['arg_type']
        # fib_fn.return_type = arg_type() # not setting the return type
        fib_fn.params[0].type = arg_type()
        c_translator = CFile("generated", [tree])

        return [c_translator]

This is how the log will look like::

    INFO:ctree.jit:detected specialized function call with arg types: [<type 'int'>]
    INFO:ctree.jit:tuner subconfig: None
    INFO:ctree.jit:arguments subconfig: {'arg_type': <class 'ctypes.c_long'>}
    INFO:ctree.jit:specialized function cache miss.
    INFO:ctree.jit:Hash miss. Running Transform
    INFO:ctree.c.nodes:file for generated C: /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpSmAfNJ/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.c
    INFO:ctree.c.nodes:generated C program: (((
    // <file: generated.c>

    void apply(long n) {
        if (n < 2) {
            return n;
        } else {
            return apply(n - 1) + apply(n - 2);
        };
    };

    )))
    INFO:ctree.c.nodes:compilation command: gcc -shared -fPIC -O2 -std=c99 -o /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpSmAfNJ/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.so /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpSmAfNJ/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.c
    /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpSmAfNJ/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.c:5:9: error: void function 'apply' should not return
          a value [-Wreturn-type]
            return n;
            ^      ~
    /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpSmAfNJ/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.c:7:29: error: invalid operands to binary expression
          ('void' and 'void')
            return apply(n - 1) + apply(n - 2);
                   ~~~~~~~~~~~~ ^ ~~~~~~~~~~~~
    2 errors generated.
    Traceback (most recent call last):
      File "fibonacci_specializer_logging.py", line 55, in <module>
        print c_fib(10), fib(10)
      File "/Library/Python/2.7/site-packages/ctree-0.1.9-py2.7.egg/ctree/jit.py", line 324, in __call__
        csf = self.finalize(transform_result, program_config)
      File "fibonacci_specializer_logging.py", line 43, in finalize
        return BasicFunction("apply", proj, entry_type)
      File "fibonacci_specializer_logging.py", line 48, in __init__
        self._c_function = self._compile(entry_name, project_node, entry_typesig)
      File "/Library/Python/2.7/site-packages/ctree-0.1.9-py2.7.egg/ctree/jit.py", line 110, in _compile
        self._module = project_node.codegen(**kwargs)
      File "/Library/Python/2.7/site-packages/ctree-0.1.9-py2.7.egg/ctree/nodes.py", line 154, in codegen
        submodule = f._compile(f.codegen())
      File "/Library/Python/2.7/site-packages/ctree-0.1.9-py2.7.egg/ctree/c/nodes.py", line 132, in _compile
        subprocess.check_call(compile_cmd, shell=True)
      File "/System/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7/subprocess.py", line 540, in check_call
        raise CalledProcessError(retcode, cmd)
    subprocess.CalledProcessError: Command 'gcc -shared -fPIC -O2 -std=c99 -o /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpSmAfNJ/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.so /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpSmAfNJ/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.c ' returned non-zero exit status 1

Since we returned a value in a void function this C code doesn't compile. We
would be able to see the compiling errors even without logging enabled but, by
having it enabled, we can inspect the generated C code and understand the
problem.

Defective C Code (Compilable)
.............................
Things get a bit harder when the code compiles. Suppose that, instead of
forgetting to set the return type we forget to set the argument type. When we
don't specify the argument type, the C compiler default the argument to ``int``
and compiles without problems:

.. code:: python

    def transform(self, tree, program_config):
        tree = PyBasicConversions().visit(tree)

        fib_fn = tree.find(FunctionDecl, name="apply")
        arg_type = program_config.args_subconfig['arg_type']
        fib_fn.return_type = arg_type()
        # fib_fn.params[0].type = arg_type() # not setting the argument type
        c_translator = CFile("generated", [tree])

        return [c_translator]

And this is how the log will look::

    INFO:ctree.jit:detected specialized function call with arg types: [<type 'int'>]
    INFO:ctree.jit:tuner subconfig: None
    INFO:ctree.jit:arguments subconfig: {'arg_type': <class 'ctypes.c_long'>}
    INFO:ctree.jit:specialized function cache miss.
    INFO:ctree.jit:Hash miss. Running Transform
    INFO:ctree.c.nodes:file for generated C: /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpIDNG44/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.c
    INFO:ctree.c.nodes:generated C program: (((
    // <file: generated.c>

    long apply(n) {
        if (n < 2) {
            return n;
        } else {
            return apply(n - 1) + apply(n - 2);
        };
    };

    )))
    INFO:ctree.c.nodes:compilation command: gcc -shared -fPIC -O2 -std=c99 -o /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpIDNG44/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.so /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpIDNG44/fib/4582712020805158851/-7985492147856592190/BasicTranslator/default/generated.c
    55 55

Once again the integer argument works. Observe our function parameter doesn't
have a type but compiles without problems since C will default to ``int``.
Because it compiles to ``int``, the integer argument works. But this is the
rest of the log::

    INFO:ctree.jit:detected specialized function call with arg types: [<type 'float'>]
    INFO:ctree.jit:tuner subconfig: None
    INFO:ctree.jit:arguments subconfig: {'arg_type': <class 'ctypes.c_double'>}
    INFO:ctree.jit:specialized function cache miss.
    INFO:ctree.jit:Hash miss. Running Transform
    INFO:ctree.c.nodes:file for generated C: /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpIDNG44/fib/4268650778531830270/-7985492147856592190/BasicTranslator/default/generated.c
    INFO:ctree.c.nodes:generated C program: (((
    // <file: generated.c>

    double apply(n) {
        if (n < 2) {
            return n;
        } else {
            return apply(n - 1) + apply(n - 2);
        };
    };

    )))
    INFO:ctree.c.nodes:compilation command: gcc -shared -fPIC -O2 -std=c99 -o /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpIDNG44/fib/4268650778531830270/-7985492147856592190/BasicTranslator/default/generated.so /var/folders/wd/0gw3tcb56575wld57r1hw6y00000gn/T/tmpIDNG44/fib/4268650778531830270/-7985492147856592190/BasicTranslator/default/generated.c
    [1]    29300 segmentation fault  python fibonacci_specializer_logging.py

The code compiles successfully but the parameter type keeps defaulting to
``int`` and that drives us to an undefined behaviour when calling the function
from python. This undefined behaviour ends in a Segmentation Fault.

You may wonder why it doesn't raise an exception like on the bug from
`Cache Misuse`_. This is due to the entry type we defined in the ``finalize``
method. In the previous example, Python could identify the problem because the
entry type had an ``int`` parameter. Here our entry type says it accepts a
``float`` while the C function actually doesn't.

This kind of problem can be hard to spot even with logging enabled. We will see
other techniques that can be applied to this problem in the following sections.

Ctree Exceptions
----------------
There are some issues that, when detected by ctree, will raise an exception.
They give us a clue on what the problem may be.

"Expected a pure C ast, but found a non-CtreeNode: %s."

"Expected a ctypes type instance, not %s, (%s):"

"No type recognizer defined for %s."

"No code generator defined for %s."

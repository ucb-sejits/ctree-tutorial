ctree-tutorial
==============

A set of tutorials that will help you start using ctree.

Table of Contents
-----------------
1. `Introduction to Specializers <1-introduction_to_specializers.rst>`_
2. `Debugging Specializers <2-debugging.rst>`_
3. `Visitors and Transformers <3-visitors_and_transformers.rst>`_
4. `Case Study: Functional Numpy <4-functional_numpy.rst>`_
5. `String Templates <5-string_templates.rst>`_

Basic Concepts
--------------
- **AST** Abstract Syntax Tree. A tree representation of a source code. This is
  the way specializers modify and convert codes.
- **JIT** Just in Time. Refers to the "just in time" compilation of the code.
  A specializer JIT compiles (compiles just in time) part of the python code
  specialized.
- **Transformer** Same as Visitor with the difference that Transformers can
  modify the tree they are traversing.
- **Visitor** A class that traverses a tree and executes actions based on the
  values of specific types of node, but without modifying them.

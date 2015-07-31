#!/bin/bash

echo "Cython: "
python setup.py build_ext --inplace &> /dev/null
python test_fib.py
echo "-----"

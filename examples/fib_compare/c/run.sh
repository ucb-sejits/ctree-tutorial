#!/bin/bash

echo "C: "

gcc -Wall -c -O2 fib.c                
gcc -Wall -c test_fib.c               
gcc -Wall -o test_fib test_fib.o fib.o
./test_fib
rm test_fib
rm *.o
echo "-----"

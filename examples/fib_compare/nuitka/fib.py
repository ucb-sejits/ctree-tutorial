import timeit


def fib(n):
    if n < 2:
        return n
    else:
        return fib(n - 1) + fib(n - 2)

print timeit.repeat('fib(40)', 'from __main__ import fib', repeat=20, number=1)

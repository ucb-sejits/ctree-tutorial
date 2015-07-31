import timeit

print timeit.repeat('fib(40)', 'from fib import fib', repeat=5, number=1)

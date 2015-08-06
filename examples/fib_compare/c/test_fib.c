
#include <stdio.h>
#include <time.h>
#include "fib.h"

int main(int argc, char const *argv[])
{
	clock_t begin, end;
	double time_spent;
	int result;

	printf("[");
	for (int i = 0; i < 20; ++i) {
		begin = clock();
		result = fib(40);
		end = clock();
		time_spent = (double)(end - begin) / CLOCKS_PER_SEC;
		printf(" %f", time_spent);
	}
	printf(" ]\n");
	return 0;
}

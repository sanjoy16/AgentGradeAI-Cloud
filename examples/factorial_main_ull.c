#include <stdio.h>

int main(void)
{
    int n;
    unsigned long long factorial = 1;

    printf("Enter a non-negative integer (0 to 20): ");
    if (scanf("%d", &n) != 1) {
        printf("Invalid input.\n");
        return 1;
    }

    if (n < 0 || n > 20) {
        printf("Please enter a number between 0 and 20.\n");
        return 1;
    }

    for (int i = 2; i <= n; ++i)
        factorial *= (unsigned long long)i;

    printf("Factorial of %d = %llu\n", n, factorial);
    return 0;
}

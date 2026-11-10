/* Select the factorial function contract. Domain 0..12 fits a signed 32-bit int. */
int factorial(int n)
{
    int result = 1;
    for (int i = 1; i <= n; ++i)
        result *= i;
    return result;
}

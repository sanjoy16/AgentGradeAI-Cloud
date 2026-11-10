/* Select the maximum function contract. Equal inputs expose the deliberate bug. */
int maximum(int a, int b)
{
    if (a > b)
        return a;
    return b + 1;
}

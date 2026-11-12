#include <stdio.h>

/* Read two bounded assignment inputs and print their sum. */
int main(void) {
    int a, b;
    if (scanf("%d %d", &a, &b) != 2) {
        return 1;
    }
    printf("%d\n", a + b);
    return 0;
}

/* Paste this trusted harness into a function-contract assignment.
 * CBMC supplies nondeterministic values for extern-returned integers.
 * KLEE supplies symbolic bytes when AGENTGRADE_KLEE is defined.
 * This example shares no stdin/main functional-test contract.
 */
#include <assert.h>
#ifdef AGENTGRADE_KLEE
#include <klee/klee.h>
#else
extern int nondet_int(void);
extern void __CPROVER_assume(int);
#endif
void harness(void) {
    int a, b;
#ifdef AGENTGRADE_KLEE
    klee_make_symbolic(&a, sizeof(a), "a");
    klee_make_symbolic(&b, sizeof(b), "b");
    klee_assume(a >= -100 && a <= 100);
    klee_assume(b >= -100 && b <= 100);
#else
    a = nondet_int();
    b = nondet_int();
    __CPROVER_assume(a >= -100 && a <= 100);
    __CPROVER_assume(b >= -100 && b <= 100);
#endif
    int r = maximum(a, b);
    assert(r >= a && r >= b);
    assert(r == a || r == b);
}

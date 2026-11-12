# Formal and symbolic checks

Verification needs a specification. Faculty must provide function harnesses defining inputs, assumptions and assertions. The framework does not infer universal correctness from an arbitrary main program.

## CBMC

```bash
docker build -f sandbox/Dockerfile -t agentgrade-sandbox:1 .
docker build -f sandbox/Dockerfile.formal -t agentgrade-formal:1 .
```

The optional AMD64 image pins official CBMC 6.11.0 and verifies its release checksum. Set `SANDBOX_FORMAL_IMAGE=agentgrade-formal:1` in `.env` and recreate the worker. The adapter selects function `harness`, unwind 32, unwinding assertions, bounds/pointer/overflow checks. Automated bounded credit requires exit 0 AND `VERIFICATION SUCCESSFUL`. Counterexamples get zero; errors/timeouts remain inconclusive.

Use `examples/cloud/maximum.c` and paste `maximum-harness.c` into the harness field. This is a function-contract example: main/stdin tests are not directly applicable; faculty must configure an appropriate exercise or explicitly resolve its functional-testing mark. A min-instead-of-max implementation should violate the assertions.

## KLEE

`sandbox/Dockerfile.symbolic` is an optional integration template based on `klee/klee:3.0`; it was not built/tested in this session. Validate upstream image availability, KLEE PATH/include paths and matching Clang/LLVM versions before enabling it.

```bash
docker build -f sandbox/Dockerfile.symbolic -t agentgrade-symbolic:1 .
```

Set `SANDBOX_SYMBOLIC_IMAGE=agentgrade-symbolic:1`. Adjust image `KLEE_CLANG`/PATH/include configuration to match its LLVM toolchain. The runner defines `AGENTGRADE_KLEE`, generates bitcode and explores entry `harness` with 30-second/128-MB budgets. The sample harness uses KLEE symbolic integers or CBMC nondeterminism according to that macro. Unsupported C/library models require reviewed trusted harness adaptations.

KLEE error files are included as evidence. No errors does not demonstrate complete coverage: symbolic credit still requires faculty judgment. Tool exit alone never establishes correctness.

## Limits

Each subprocess has a 5-second CPU limit, a 1-MB output-file limit and bounded captured evidence; container wall/memory/CPU/process limits also apply. Larger verification exercises may hit CPU limits before their wall timeout. Increase limits only with reviewed capacity and tests. Missing tools/harnesses produce unavailable; incomplete analyses are never passes. Static heuristics do not prove asymptotic complexity or comprehensive security.

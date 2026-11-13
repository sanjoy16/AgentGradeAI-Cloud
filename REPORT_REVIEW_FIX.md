# Factorial report review and runtime repair

Reviewed GradeAI_approved_lnDCQEbFXyMFTHsyystTnWyE.pdf (approved 77/100).

## Findings
- LLVM/KLEE cannot run without Docker CLI in the application process. Installing tools on the Mac does not install them inside the Docker web app.
- Z3 and CBMC were unavailable. These are dependency outcomes, not proof that the submission is correct or incorrect.
- Open-main safety does not check factorial output correctness. The 15 testing points are held, not a demonstrated wrong answer.
- The submitted scanf at line 8 does not check its return value; failed input leaves n uninitialized.
- The factorial loop at lines 14–15 accepts n above 20 and wraps unsigned long long on the usual 64-bit representation. INT_MAX can also overflow the signed loop increment. These are source-review observations, not new KLEE/CBMC execution results.
- Function-count and variable-scope deductions remain heuristic and require faculty moderation.

## Changes
- doctor.py --require-all now exits unsuccessfully if a required dependency is unavailable.
- The Mac launcher repairs common Homebrew/Docker PATH omissions, requires preflight success, and selects a free port in 8502–8522 (or AGENTGRADE_PORT).
- Faculty dependency checks explain container/host isolation and distinguish a missing CLI, stopped Docker engine, and missing KLEE image.
- CBMC now enables unsigned-overflow checking in addition to signed overflow. Unsigned wrap is defined by C: a finding requires review against the assignment, rather than automatic deduction.
- examples/factorial_main_ull.c is the checked-input, 0..20 example. It already existed in the package; regression tests now compile it strictly and check 0, 1, 5, 20, -1, 21, nonnumeric input and EOF. The integer-token safety model does not verify arbitrary text parsing or output correctness.

## Run on macOS
1. Open Docker Desktop and wait for its engine.
2. Open Terminal and change into this updated project folder.
3. Run: bash run-mac.command
4. Open the exact localhost URL printed by the launcher (port may differ from 8502).
5. Submit a NEW assessment. Existing approved reports are retained unchanged.
6. For main-only submissions select Open C safety. For functional verification use the exact factorial function contract (int factorial(int n), 0..12); examples/factorial.c matches it. Do not select that contract for the unsigned-long-long main-only example.
7. Review actual stage outcomes and scope before approving the new PDF.

The legacy Dockerfile remains a GCC/Cppcheck web-app profile. Full verification uses the native Mac launcher plus the Docker KLEE worker; this update does not install host tools into that web container. An all-true dependency preflight checks availability, not tool compatibility or completion of a submission. Inspect each actual analysis result.

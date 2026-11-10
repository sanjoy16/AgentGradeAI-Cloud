# Bounded string and multiple integer input support

The Student Marks Processor report blocked LLVM, KLEE, Z3 and CBMC because the
old adapter only accepted single %d scanf calls. Its scanf("%63s", buf) triggered
an early return from the entire verification pipeline. This is a model limitation,
not a demonstrated defect in the submitted code.

## Changes

- Support literal %d and width-limited %Ns strings, including calls such as
  scanf("%d %d", &a, &b) and scanf("%d %63s", &n, buf).
- Permit up to eight whitespace-separated conversions per call and string widths
  from 1 to 256. The caller still needs enough destination storage. Out-of-bounds
  writes are not suppressed by the model.
- Model successful, partial, failed and EOF assignment counts. Only successfully
  assigned destinations are written. Strings have non-NUL/non-whitespace bytes,
  length 1..N, and a terminating zero byte.
- Keep unsupported formats explicit: floats, unbounded %s, scansets, dynamic
  format expressions and unsupported modifiers require a trusted harness.
- Generate LLVM independently even if the input model is unsupported.
- Preserve unwinding assertions; raise the CBMC bound to cover the string-model
  loop (64 for %63s). Student loops can still exhaust the configured bound.
- Display input-scope limits and advice to run a fresh assessment.

## Scope

This is an independent-token abstraction, not an exact implementation of scanf.
It does not model persistent stream state across calls, textual numeric parsing,
locale or printed output. Failure paths may be over-approximated. Defect findings
need inspection or concrete replay. It must not be described as proof that the
entire interactive program is correct. Open-main mode remains safety-only and
continues to withhold functional-correctness credit pending an explicit contract.

## Update and run on the Mac

1. Stop the native app with Control-C. Extract the corrected source into the
   existing project folder, preserving data/agentgrade.db and .venv.
2. Open Docker Desktop and wait for its engine to run.
3. In that project folder run: bash run-mac.command
4. Check the health summary; GCC, Cppcheck, CBMC, Z3, Docker engine and KLEE image
   must be available. Open http://localhost:8502.
5. Upload the program again with the Open C safety profile and keep the new
   submission ID. Review all newly collected evidence, then approve if appropriate.

The ordinary Docker web image at port 8501 installs GCC and Cppcheck, not the full
verification runtime. This source update does not install host tools inside that
container. Use the Mac launcher above for the supported integrated configuration.

Old approved PDFs and stored assessments retain their historical outcomes and
marks. Re-downloading one does not execute the tools. A newly supported format
can still yield INCONCLUSIVE, VIOLATED or REVIEW REQUIRED when the actual tools
find an error, reach a limit or cannot model another part of the program.

## Validation

Run python -m unittest discover -q from this directory. Regression tests compile
both generated backends with strict GCC, execute the token shim with deterministic
choices to check failure/EOF/partial reads and a 63-byte boundary string, and mock
worker artifacts to check dispatch, SMT replay and unwind configuration. These
adapter tests are not a new KLEE or CBMC run on the student's 109-line program.

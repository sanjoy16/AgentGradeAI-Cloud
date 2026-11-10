# Review of REPORT1

The report records a genuine local run of Clang/LLVM, KLEE, Z3, CBMC,
the evidence graph, retrieval and history summary. The approved score adds up
correctly: 32 + 0 + 7 + 20 + 15 = 74.

## Corrections

1. KLEE warned that __isoc99_scanf was unresolved, called it externally and
   reached only the invalid-input path. A zero-error result from that run
   cannot establish coverage of the valid factorial inputs. The classifier now
   treats those warnings as INCONCLUSIVE even when all started paths completed.
2. New safety-mode submissions using literal single-conversion scanf("%d", &int)
   receive a documented symbolic integer-token model. It represents success,
   matching failure and EOF. Printf is abstracted with a nondeterministic return.
   This excludes raw text parsing, formatted-output safety and expected-output
   correctness. Other scanf formats are blocked for an instructor-authored model.
3. The original bound of 16 did not cover all iterations for accepted input 20.
   The default CBMC bound is now 32, keeping unwinding assertions enabled.
   This change requires a new verification run; it does not retrospectively
   turn an unwinding failure into a proof.
4. The submitted accumulator is unsigned long long. With a 64-bit range,
   20! fits and 21! does not. Retrieved notes now select this case rather than
   the signed-int factorial limit of 12. The original source's input guard 0..20
   is appropriate for this representation.
5. The main prototype warning is fixed in examples/factorial_main_ull.c.
   Original submitted source is retained in historical assessment records.
6. New report excerpts show failed properties and completion summaries before
   repeated library-success messages. The evidence appendix no longer repeats
   all raw logs. Evidence counts include the analytics record.
7. Re-exporting an old assessment corrects interpretations from its stored
   warnings and adds review notes. Approved marks and approval time are retained.
   No new tool result is claimed for an old assessment.

## Update without losing current native submissions

Stop the running native Streamlit process with Control-C in its Terminal.
Extract the new ZIP over the SAME AgentGradeAI-full folder.
The archive contains no database or .venv, so it does not replace local data.
Run bash run-mac.command again and open http://localhost:8502.

For fresh verification, submit examples/factorial_main_ull.c with Open C program
safety checks on main, inspect the outcomes and obtain a new faculty approval.
Open-main mode still checks safety rather than mathematical output correctness.
The function-contract profile int factorial(int n) remains a different 0..12
signed-int assignment.

## Validation

19 regression checks ran, with 17 passing and 2 skipped because optional
Streamlit/Z3 test dependencies were absent in the review environment.
New tests cover the observed scanf-warning regression, historical report
reinterpretation without mark changes, I/O harness syntax, unsupported scanf
formats, unsigned range guidance and the bound.
GCC syntax-checked both generated main harnesses and executed the supplied
factorial example on inputs 0, 5, 20, 21 and invalid text with expected outcomes.
PDF checks confirmed corrected labels and preservation of approved marks.
KLEE and CBMC are not installed in this build environment; their corrected
harness execution and final verdicts still require a run on the Mac.

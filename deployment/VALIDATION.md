# Validation record — 12 November 2026

Validated in the managed Linux cloud development environment, not a provisioned production host.

- Application tests: 12 passed. Coverage includes registration role enforcement, authentication, draft confidentiality, cross-student access denial, approval/PDF workflow, invalid/non-finite marks, immutable publication, rubric/test snapshots, upload validation, HTML escaping, CSRF, assignment closure and unavailable-tool scoring.
- Real isolated execution: 1 sandbox integration test passed under gVisor `runsc`. Tested successful C17 compilation, two correct input/output cases, syntax failure, nonzero runtime exit, infinite-loop timeout, absent Docker socket and absent session secret in student processes.
- Full end-to-end integration passed with real gVisor evidence: student upload, persistent queue processing, hidden tests, confidential draft, faculty mark resolution/approval and an approved student PDF (7,916 bytes).
- CBMC 6.11.0 optional image built from checksum-verified official package. Actual bounded maximum-function harness verified; a minimum-instead-of-maximum mutation returned exit 10 and an assertion failure.
- Cloud web/worker Docker image built successfully. A subsequent container smoke launch exceeded this environment's disk quota; full deployed-container startup is not verified.
- Compose configuration validated with non-production placeholder settings. Python modules compile and Git whitespace checks pass.
- KLEE optional image was not built or tested. AI model calls were not exercised because no API credential was supplied.
- Interactive browser QA was skipped: the managed Sites environment had no `cua_repl.js`, and its skill forbids substituting another browser-control path. Server-rendered HTML and route workflows were checked through Flask's test client.
- Production PostgreSQL/Redis/Caddy deployment, real DNS/TLS and external student access remain unverified because no hosting account/domain is configured.

The existing Streamlit prototype was preserved. Its legacy test suite was not part of the new cloud-platform validation.

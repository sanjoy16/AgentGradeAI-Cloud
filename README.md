# AgentGradeAI-Cloud

Python cloud application for C programming assessment: student accounts, isolated execution, independent specialist evaluation agents, configurable grading, faculty approval and downloadable PDF reports.

The cloud application is in `cloudgrade/` (Flask, SQLAlchemy, PostgreSQL and a durable database queue). The existing Streamlit research prototype remains in `app.py`; its original instructions are in [README-legacy.md](README-legacy.md). The root Dockerfile still builds that prototype. Use `deployment/Dockerfile` for the cloud platform. The cloud database is separate and does not migrate legacy records.

## Features

- Public student registration, personal details, assignment title/notes and UTF-8 C upload (64 KB maximum).
- CLI-provisioned faculty accounts; public registration cannot grant faculty privileges.
- Faculty-authored assignments, hidden tests, configurable rubric and optional function-contract harness.
- Persistent queue, atomic job claims, attempt tokens, interrupted-job detection and faculty retry.
- GCC compilation, UBSan functional tests, Cppcheck, Clang security analysis, explicit style heuristics, optional CBMC/KLEE adapters and independent AI specialty commentary.
- Draft confidentiality enforced server-side. Faculty resolves every mark, adds feedback/rationale and approves publication atomically.
- Student access to own approved results/PDF only; immutable published snapshots, original evidence and audit trail.
- Responsive student/faculty dashboards, HTTPS deployment, CSRF protection, password hashing and request throttling.

## Deploy on a cloud Linux server

Students need only a browser. The server needs Docker Engine, Compose, gVisor `runsc`, a real public domain and at least 4 vCPUs, 8 GB RAM and 40 GB disk.

```bash
cp .env.example .env
# Fill with independent random secrets and your domain; never commit .env.
docker build -f sandbox/Dockerfile -t agentgrade-sandbox:1 .
docker compose build
docker compose up -d db redis
docker compose run --rm web flask --app cloudgrade init-db
docker compose run --rm web flask --app cloudgrade create-faculty
docker compose run --rm web flask --app cloudgrade seed-assignment
docker compose up -d
```

Point DNS at the VM and allow 80/443. Caddy obtains HTTPS certificates. Visit `https://YOUR_DOMAIN`, register a student and submit `examples/cloud/sum.c`. Sign in separately as faculty to review and publish. No default credentials are supplied.

See [deployment](deployment/DEPLOYMENT.md), [architecture](deployment/ARCHITECTURE.md), [verification](deployment/VERIFICATION.md) and [validation](deployment/VALIDATION.md).

## Transparent scoring

| Agent | Default points | Method / limitation |
|---|---:|---|
| Compilation | 15 | GCC C17, Wall/Wextra/Wpedantic |
| Functionality | 30 | Faculty stdin tests; UBSan; trimmed exact output |
| Quality | 15 | Explicit structural/style heuristics |
| Complexity | 10 | Token observations; faculty must judge actual complexity |
| Optimization | 10 | Cppcheck diagnostics; no benchmark claim |
| Security | 10 | Clang analyzer and unsafe API patterns; no security proof |
| Best practices | 5 | Explicit heuristic checks |
| Formal verification | 3 | Optional CBMC, trusted bounded harness |
| Symbolic execution | 2 | Optional KLEE; coverage needs faculty interpretation |

Each assignment's integer weights must total 100. The final score is the sum of agent marks, each bounded by its weight. Missing checks have null provisional marks; their points are unawarded, never redistributed. Faculty explicitly enters every score, including zero when credit is unsupported. Tests and rubric are snapshotted on submission. Override rationale and original marks are preserved.

## AI agents

Configure `OPENAI_API_KEY` in the worker's protected environment to enable separate model calls for each specialty. `OPENAI_MODEL` is configurable. Calls receive agent summaries, not raw source, hidden tests or identity. Model commentary cannot change scores, execute commands or approve results. Without a key the tool-assisted pipeline works and reports AI agents as disabled. No AI credential was supplied in this session.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-cloud.txt
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export COOKIE_SECURE=false  # localhost HTTP only
.venv/bin/flask --app cloudgrade init-db
.venv/bin/flask --app cloudgrade create-faculty
.venv/bin/flask --app cloudgrade seed-assignment
.venv/bin/flask --app cloudgrade run --port 8000
# Another shell with identical environment:
.venv/bin/python -m cloudgrade.worker
```

SQLite is for development; production uses PostgreSQL and Redis. Worker and web must share the database and session configuration.

```bash
python -m pytest tests/cloud -q
RUN_SANDBOX_TESTS=1 TEST_SANDBOX_RUNTIME=runsc python -m pytest tests/cloud -q
```

CI additionally tests Docker isolation using its default runtime; this test setting does not change production's gVisor requirement.

## Deployment status and remaining integrations

**No persistent public deployment has been provisioned.** GitHub is connected, but this session has no cloud-hosting account, domain or production secrets. Available Sites hosting cannot run this Python service or native C workers; a static substitute is not presented as the assessment portal.

The default sandbox includes GCC, Cppcheck and Clang. Optional CBMC/KLEE images require separate setup and verification. Missing tools are never reported as successful checks. General correctness cannot be inferred without a specification. Email verification, password-reset delivery, institutional SSO/MFA, multi-file uploads, LMS integration, schema migrations beyond initialization and institution-specific retention automation remain enhancements.

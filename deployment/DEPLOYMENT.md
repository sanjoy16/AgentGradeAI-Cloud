# Deployment and maintenance

## Prerequisites

Provide a Linux AMD64 cloud VM (4 vCPU, 8 GB RAM, 40 GB disk minimum), administrator access, domain/DNS access and a hosting account. No hosting credential or public domain is configured in this session. GitHub access alone cannot provision the public service.

Install Docker Engine/Compose and gVisor following https://gvisor.dev/docs/user_guide/install/. Register Docker's `runsc` runtime, preserving existing daemon settings. Confirm it appears in `docker info`. Use a dedicated host; only expose HTTPS/HTTP, restrict SSH and never expose Docker/Postgres/Redis.

```bash
git clone https://github.com/sanjoy16/AgentGradeAI-Cloud.git
cd AgentGradeAI-Cloud
git checkout feat/cloud-assessment-platform
cp .env.example .env
chmod 600 .env
```

Generate two separate hex secrets with `python3 -c 'import secrets; print(secrets.token_hex(32))'` and fill `SECRET_KEY` and `POSTGRES_PASSWORD`. Hex is URL-safe for the database connection string. Set `DOMAIN` to a real DNS name pointing to the VM. Keep secrets in a protected environment file or hosting secret manager, never commits or chat.

## Launch

```bash
docker build -f sandbox/Dockerfile -t agentgrade-sandbox:1 .
docker compose build
docker compose up -d db redis
docker compose run --rm web flask --app cloudgrade init-db
docker compose run --rm web flask --app cloudgrade create-faculty
docker compose run --rm web flask --app cloudgrade seed-assignment
docker compose config --quiet
docker compose up -d
```

Faculty creation prompts privately for a password. The optional seed command adds a sample assignment only on an empty assignment database. Create institution-specific tests in the faculty dashboard. Build sandbox images on the same daemon mounted into the worker. `runsc` fails closed when unavailable; never disable isolation to make public grading work.

Caddy obtains/renews HTTPS certificates; allow ports 80/443 and configure DNS first. Do not publish port 8000 directly. In managed proxy environments, builds can use the Dockerfiles' optional `--secret id=proxy_ca,src=/path/to/combined-ca-bundle`; do not disable TLS verification.

## Acceptance

Visit `/healthz`, register two students and sign in as faculty in separate browser sessions. Submit `examples/cloud/sum.c`, refresh to pending review and verify draft marks/PDF are inaccessible. The second student must receive 404 for the first student's record/source/report. Faculty resolves every mark, adds feedback/rationale and approves. Only then can the owner download the PDF. Test syntax errors, wrong output and infinite loops. Enable CBMC/KLEE only after separate toolchain checks in VERIFICATION.md.

## Operations

```bash
docker compose ps
docker compose logs --tail=100 web worker
docker compose restart worker
docker compose exec -T db pg_dump -U agentgrade -Fc agentgrade > agentgrade-backup.dump
```

Encrypt daily backups, store them off-host and test restoration. On a new/stopped deployment restore with `pg_restore -U agentgrade -d agentgrade --clean --if-exists` through the database container. Logs can contain student diagnostics; restrict access. Never run `docker compose down -v` on live data. Changing `.env` alone does not rotate an existing PostgreSQL role password.

Before updates: back up, review source changes, run tests, rebuild, apply reviewed schema migrations if needed and recreate services. Pin grading image digests in production and record tool versions. Session secret rotation logs users out. Monitor queue age, failed jobs, disk pressure, runtime failures and backup success. Faculty can retry failed assessments; no restart publishes unreviewed work.

For scale, use a private managed PostgreSQL database with TLS, shared private Redis and isolated grading hosts. Customize `DATABASE_URL` and `RATE_LIMIT_STORAGE_URI`; the supplied Compose is a single-host reference. Add institution-approved identity management before broad enrollment: email verification, SSO/MFA and email password reset are not implemented. Establish quotas, data retention and administrator account recovery policies.

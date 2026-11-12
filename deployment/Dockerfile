FROM python:3.12-slim AS web
WORKDIR /app
COPY requirements-cloud.txt .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements-cloud.txt
COPY cloudgrade ./cloudgrade
RUN useradd --uid 10001 --create-home app && chmod -R a+rX /app
USER 10001:10001
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--access-logfile", "-", "cloudgrade:create_app()"]

FROM web AS worker
USER root
RUN apt-get update && apt-get install -y --no-install-recommends docker.io && rm -rf /var/lib/apt/lists/*
# Worker holds Docker daemon authority. Run only on a dedicated grading host.
CMD ["python", "-m", "cloudgrade.worker"]

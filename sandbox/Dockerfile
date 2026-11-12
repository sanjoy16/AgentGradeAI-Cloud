FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev cppcheck clang llvm python3 && rm -rf /var/lib/apt/lists/*
COPY --chmod=0444 sandbox/runner.py /opt/runner.py
USER 65534:65534
WORKDIR /work
ENTRYPOINT ["python3", "-I", "/opt/runner.py"]

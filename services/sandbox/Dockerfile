# Sandbox image: runs ONE submission's pytest session in isolation.
# Pinned base (no :latest). Single concern, so multi-stage is just a thin
# builder that installs pytest into a venv copied into a clean runtime.

# --- builder ---------------------------------------------------------------
FROM python:3.13.1-slim-bookworm AS builder

WORKDIR /build

# Install only pytest into an isolated venv. No project deps: user code is
# graded against plain pytest, nothing else is importable on purpose.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir "pytest==8.3.4"

# --- runtime ---------------------------------------------------------------
FROM python:3.13.1-slim-bookworm AS runtime

# Unprivileged user — the container also runs with --cap-drop=ALL from the host.
RUN useradd --create-home --uid 10001 sandbox

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY runner/run_tests.py /app/run_tests.py

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER sandbox

# stdout carries the JSON result payload; the host kills us on wall-clock timeout.
ENTRYPOINT ["python", "/app/run_tests.py"]

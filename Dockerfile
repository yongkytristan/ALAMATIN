# ALAMATIN single-address quality gate.
#
# Python 3.11 is required, not merely preferred: the codebase uses
# dataclass(slots=True), which is 3.10+, and the deploy target's system python3
# is 3.9. Pinning the base image here removes that difference.
FROM python:3.11-slim AS base

# Fail fast and keep the image free of build caches.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Dependencies first so a source change does not re-resolve them.
# --require-hashes is deliberate: the repository policy requires exact,
# hash-verified dependencies, and this is the only step that needs network
# access. Runtime needs none.
COPY requirements.lock ./
RUN if grep -qE '^[[:space:]]*[^[:space:]#]' requirements.lock; then \
        python -m pip install --require-hashes -r requirements.lock; \
    else \
        echo "requirements.lock declares no dependencies; skipping install."; \
    fi

# Only what the service needs to run. Tests, docs, and notebooks are excluded by
# .dockerignore; the one governed data file the pipeline loads at import time is
# named explicitly rather than copying data/ wholesale.
COPY src ./src
COPY contracts ./contracts
COPY data/processed/jabar-reference-v1-verified.json ./data/processed/
COPY scripts/verify_clean_clone.py ./scripts/

# Refuse to build an image that cannot start. Without this the failure would
# surface as a restarting container instead of a failed build.
RUN python -c "import alamatin.service" \
    && echo "import check passed"

# Runs unprivileged: the service reads a reference file and writes nothing.
RUN useradd --create-home --uid 10001 alamatin \
    && chown -R alamatin:alamatin /app
USER alamatin

EXPOSE 8000

# Uses the stdlib rather than adding curl. A 503 means the app is alive but a
# critical dependency failed, which is a real failure for a healthcheck even
# though the process is up.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import sys,urllib.request;\
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "uvicorn", "alamatin.service:app", "--host", "0.0.0.0", "--port", "8000"]

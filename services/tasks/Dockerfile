# Build stage: resolve everything into a self-contained virtualenv.
# Sources, pip's cache and setuptools' build artifacts stay in this stage.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /src

COPY common/ ./common/
RUN pip install ./common

COPY services/tasks/ ./services/tasks/
RUN pip install ./services/tasks

# Runtime stage: the virtualenv and nothing else. The worker imports
# tracker_tasks from site-packages, so it needs no files from the repo.
FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --system --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
USER app

CMD ["python", "-m", "tracker_tasks"]

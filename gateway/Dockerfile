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

COPY gateway/ ./gateway/
RUN pip install ./gateway

# Runtime stage: the virtualenv plus the two asset trees the app opens by
# relative path (main.py mounts "static", web.py renders from "templates"),
# which is why WORKDIR has to stay the directory those names resolve from.
FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --system --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app/gateway
COPY gateway/static/ ./static/
COPY gateway/templates/ ./templates/

USER app

EXPOSE 8000

CMD ["uvicorn", "tracker_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]

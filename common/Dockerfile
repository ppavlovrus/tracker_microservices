# Build stage: alembic and its SQLAlchemy/psycopg2 tooling live in the
# [migrations] extra, so only this one-shot container carries them.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /src

COPY common/ ./common/
RUN pip install "./common[migrations]"

# Runtime stage: the virtualenv plus the migration scripts themselves.
# alembic.ini points at a relative script_location, so WORKDIR must be the
# directory holding it.
FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --system --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app/common
COPY common/alembic.ini ./alembic.ini
COPY common/alembic/ ./alembic/

USER app

CMD ["alembic", "upgrade", "head"]

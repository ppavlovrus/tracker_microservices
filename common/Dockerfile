FROM python:3.12-slim

WORKDIR /app

COPY common/ ./common/
RUN pip install "./common[migrations]"

WORKDIR /app/common

CMD ["alembic", "upgrade", "head"]
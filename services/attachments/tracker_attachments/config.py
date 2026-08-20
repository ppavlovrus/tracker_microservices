"""Attachments Service configuration."""

import os

# RabbitMQ settings
AMQP_URL: str = os.getenv("AMQP_URL", "amqp://guest:guest@localhost/")

# Database settings
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_NAME: str = os.getenv("DB_NAME", "task_tracker")
DB_USER: str = os.getenv("DB_USER", "postgres")
DB_PASSWORD: str = os.getenv("DB_PASSWORD", "qwerty")

# Connection pool settings
DB_POOL_MIN_SIZE: int = int(os.getenv("DB_POOL_MIN_SIZE", "5"))
DB_POOL_MAX_SIZE: int = int(os.getenv("DB_POOL_MAX_SIZE", "20"))

# Service settings
SERVICE_NAME: str = "attachments-service"
QUEUE_NAME: str = "attachments.commands"
PREFETCH_COUNT: int = int(os.getenv("PREFETCH_COUNT", "10"))

# S3 / MinIO settings
# Internal endpoint is used for server-side operations (bucket, delete).
# Public endpoint is what presigned URLs point to, so it must be reachable
# by the client that ultimately uploads/downloads the bytes.
S3_ENDPOINT_INTERNAL: str = os.getenv("S3_ENDPOINT_INTERNAL", "http://minio:9000")
S3_ENDPOINT_PUBLIC: str = os.getenv("S3_ENDPOINT_PUBLIC", "http://localhost:9000")
S3_ACCESS_KEY: str = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY: str = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_BUCKET: str = os.getenv("S3_BUCKET", "attachments")
S3_REGION: str = os.getenv("S3_REGION", "us-east-1")
S3_PRESIGN_EXPIRE: int = int(os.getenv("S3_PRESIGN_EXPIRE", "3600"))

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

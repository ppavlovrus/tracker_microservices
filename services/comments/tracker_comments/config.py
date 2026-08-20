"""Comments Service configuration."""

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
SERVICE_NAME: str = "comments-service"
QUEUE_NAME: str = "comments.commands"
PREFETCH_COUNT: int = int(os.getenv("PREFETCH_COUNT", "10"))

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

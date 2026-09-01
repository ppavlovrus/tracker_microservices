"""Users Service configuration."""

import os

from task_tracker_common.contracts.queues import Queue

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
SERVICE_NAME: str = "users-service"
# The queue name is protocol, not deployment: both sides read it from the
# same enum so a rename cannot be applied to one half of the bus.
QUEUE_NAME: str = Queue.USERS
PREFETCH_COUNT: int = int(os.getenv("PREFETCH_COUNT", "10"))

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

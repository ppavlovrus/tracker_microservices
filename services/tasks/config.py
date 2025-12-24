"""Configuration for Tasks Service."""

import os

# Database configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "qwerty")
DB_NAME = os.getenv("DB_NAME", "task_tracker")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Database pool configuration
DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "5"))
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "20"))
DB_POOL_COMMAND_TIMEOUT = int(os.getenv("DB_POOL_COMMAND_TIMEOUT", "60"))
DB_POOL_MAX_QUERIES = int(os.getenv("DB_POOL_MAX_QUERIES", "50000"))
DB_POOL_MAX_INACTIVE_LIFETIME = int(os.getenv("DB_POOL_MAX_INACTIVE_LIFETIME", "300"))

# RabbitMQ configuration
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = os.getenv("RABBITMQ_PORT", "5672")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")

AMQP_URL = f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/"

# Queue name
QUEUE_NAME = os.getenv("QUEUE_NAME", "tasks.commands")



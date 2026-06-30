"""Gateway configuration."""

import os
from typing import Optional

# RabbitMQ settings
AMQP_URL: str = os.getenv("AMQP_URL", "amqp://guest:guest@localhost/")
RPC_TIMEOUT: float = float(os.getenv("RPC_TIMEOUT", "30.0"))

# Gateway settings
SERVICE_NAME: str = "gateway"
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))

# Redis cache settings
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_TTL_TASK: int = int(os.getenv("CACHE_TTL_TASK", "60"))
CACHE_TTL_TAGS: int = int(os.getenv("CACHE_TTL_TAGS", "300"))
# Short TTL for the paginated tasks list: it self-expires instead of being
# invalidated, since a single write can land on any page.
CACHE_TTL_TASKS_LIST: int = int(os.getenv("CACHE_TTL_TASKS_LIST", "20"))

# Rate limiting settings (token-bucket, per client IP)
RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
# Bucket capacity = max burst of requests allowed at once.
RATE_LIMIT_CAPACITY: int = int(os.getenv("RATE_LIMIT_CAPACITY", "60"))
# Refill rate in tokens per second = sustained allowed request rate.
RATE_LIMIT_REFILL_RATE: float = float(os.getenv("RATE_LIMIT_REFILL_RATE", "10"))

# Metrics. When enabled, Prometheus metrics are exposed at GET /metrics.
METRICS_ENABLED: bool = os.getenv("METRICS_ENABLED", "true").lower() == "true"

# Authentication (session cookie backed by Redis).
# When enabled, write requests (POST/PUT/PATCH/DELETE) require a valid session.
AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "true").lower() == "true"
# Session lifetime in seconds (also the Redis TTL). Default: 1 day.
SESSION_TTL: int = int(os.getenv("SESSION_TTL", "86400"))
SESSION_COOKIE_NAME: str = os.getenv("SESSION_COOKIE_NAME", "session")
# Set the Secure flag on the session cookie (enable behind HTTPS).
COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

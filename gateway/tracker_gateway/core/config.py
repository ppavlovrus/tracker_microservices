"""Gateway configuration."""

import os

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

# Yandex OAuth (authorization code flow). Disabled unless both the client id
# and the secret are provided. Register the app at https://oauth.yandex.ru.
YANDEX_CLIENT_ID: str = os.getenv("YANDEX_CLIENT_ID", "")
YANDEX_CLIENT_SECRET: str = os.getenv("YANDEX_CLIENT_SECRET", "")
YANDEX_OAUTH_ENABLED: bool = bool(YANDEX_CLIENT_ID and YANDEX_CLIENT_SECRET)
# Must match the Redirect URI registered with the Yandex app exactly.
YANDEX_REDIRECT_URI: str = os.getenv("YANDEX_REDIRECT_URI", "http://localhost:8000/auth/yandex/callback")
# Yandex endpoints, overridable so e2e tests can point at a mock server.
YANDEX_OAUTH_BASE_URL: str = os.getenv("YANDEX_OAUTH_BASE_URL", "https://oauth.yandex.ru")
YANDEX_USERINFO_URL: str = os.getenv("YANDEX_USERINFO_URL", "https://login.yandex.ru/info")
# Lifetime of the one-time state token guarding the flow against CSRF.
OAUTH_STATE_TTL: int = int(os.getenv("OAUTH_STATE_TTL", "600"))
# Timeout for outgoing HTTP calls to Yandex.
OAUTH_HTTP_TIMEOUT: float = float(os.getenv("OAUTH_HTTP_TIMEOUT", "10.0"))

# Chat (WebSocket + Redis pub/sub). One shared room; live delivery goes
# through pub/sub so the chat survives scaling the gateway horizontally.
CHAT_ENABLED: bool = os.getenv("CHAT_ENABLED", "true").lower() == "true"
CHAT_CHANNEL: str = os.getenv("CHAT_CHANNEL", "chat:general")
# How many recent messages are kept in Redis and replayed on connect.
CHAT_HISTORY_SIZE: int = int(os.getenv("CHAT_HISTORY_SIZE", "50"))
# Send a ping after this many seconds of silence from the client.
CHAT_HEARTBEAT_INTERVAL: float = float(os.getenv("CHAT_HEARTBEAT_INTERVAL", "25"))
# Close the connection after this many seconds without any client frame.
CHAT_HEARTBEAT_TIMEOUT: float = float(os.getenv("CHAT_HEARTBEAT_TIMEOUT", "60"))
CHAT_MAX_MESSAGE_LENGTH: int = int(os.getenv("CHAT_MAX_MESSAGE_LENGTH", "1000"))

# SSE task notifications (Server-Sent Events + Redis pub/sub). Live task events
# (created/updated/deleted) are pushed to connected browsers over a one-way
# stream; delivery goes through pub/sub so it survives scaling the gateway.
# Unlike the chat, events are ephemeral: nothing is replayed on connect.
SSE_ENABLED: bool = os.getenv("SSE_ENABLED", "true").lower() == "true"
SSE_CHANNEL: str = os.getenv("SSE_CHANNEL", "events:tasks")
# Emit a keep-alive comment after this many seconds of silence so idle streams
# stay open through proxies and disconnects are noticed promptly.
SSE_HEARTBEAT_INTERVAL: float = float(os.getenv("SSE_HEARTBEAT_INTERVAL", "25"))
# Cap of pending events buffered per connection; a slow client is dropped
# rather than allowed to grow memory without bound.
SSE_MAX_QUEUE: int = int(os.getenv("SSE_MAX_QUEUE", "100"))

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

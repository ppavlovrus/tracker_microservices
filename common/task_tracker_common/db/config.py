"""Database configuration."""
import os

# Database connection configuration
DATABASE_USERNAME: str = os.getenv("DATABASE_USERNAME", "postgres")
DATABASE_PASSWORD: str = os.getenv("DATABASE_PASSWORD", "qwerty")
DATABASE_HOST: str = os.getenv("DATABASE_HOST", "localhost")
DATABASE_PORT: int = int(os.getenv("DATABASE_PORT", "5432"))
DATABASE_NAME: str = os.getenv("DATABASE_NAME", "task_tracker")
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"postgresql://{DATABASE_USERNAME}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
)

# asyncpg connection pool configuration
# Minimum number of connections in the pool
DB_POOL_MIN_SIZE: int = int(os.getenv("DB_POOL_MIN_SIZE", "5"))

# Maximum number of connections in the pool
DB_POOL_MAX_SIZE: int = int(os.getenv("DB_POOL_MAX_SIZE", "20"))

# Command execution timeout in seconds (None = no timeout)
DB_POOL_COMMAND_TIMEOUT: float = float(os.getenv("DB_POOL_COMMAND_TIMEOUT", "60.0"))

# Maximum number of queries per connection before recycling
# Helps prevent memory leaks and connection issues
DB_POOL_MAX_QUERIES: int = int(os.getenv("DB_POOL_MAX_QUERIES", "50000"))

# Maximum connection idle time in seconds before closing (None = never close)
DB_POOL_MAX_INACTIVE_LIFETIME: float = float(
    os.getenv("DB_POOL_MAX_INACTIVE_LIFETIME", "300.0")
)

# Connection timeout in seconds
DB_POOL_CONNECTION_TIMEOUT: float = float(
    os.getenv("DB_POOL_CONNECTION_TIMEOUT", "10.0")
)
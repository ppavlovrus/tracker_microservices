import os

# Database configuration
DATABASE_USERNAME: str = os.getenv("DATABASE_USERNAME", "postgres")
DATABASE_PASSWORD: str = os.getenv("DATABASE_PASSWORD", "qwerty")
DATABASE_HOST: str = os.getenv("DATABASE_HOST", "localhost")
DATABASE_PORT: int = int(os.getenv("DATABASE_PORT", 5432))
DATABASE_NAME: str = os.getenv("DATABASE_NAME", "test_base")
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"postgresql://{DATABASE_USERNAME}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
)
print("Created DB url:")
print (DATABASE_URL)

DB_POOL_MIN_SIZE: int = 1
DB_POOL_MAX_SIZE: int = 10
DB_POOL_COMMAND_TIMEOUT: int = 5
DB_POOL_MAX_QUERIES: int = 50000
DB_POOL_MAX_INACTIVE_LIFETIME: int = 300

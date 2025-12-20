"""Application configuration."""
import os

# Database configuration
DATABASE_USERNAME: str = os.getenv("DATABASE_USERNAME", "postgres")
DATABASE_PASSWORD: str = os.getenv("DATABASE_PASSWORD", "qwerty")
DATABASE_HOST: str = os.getenv("DATABASE_HOST", "localhost")
DATABASE_PORT: int = int(os.getenv("DATABASE_PORT", 5432))
DATABASE_NAME: str = os.getenv("DATABASE_NAME", "task_tracker")
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"postgresql://{DATABASE_USERNAME}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
)
print (DATABASE_URL)
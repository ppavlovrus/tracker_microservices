"""
This is the alembic env file
This file is needed for alembic, to run migrations
alembic use sqlalchemy engine and take database settings from src/config
Specific alembic settings placed in alembic.ini
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
print(sys.path)
from db.config import DATABASE_URL
print("____")
print(DATABASE_URL)

# Import models from database.models
from db.models import Base

from db.models import (  # noqa: F401
    TaskStatus,
    Tag,
    Task
)

"""SQLAlchemy models for Alembic migrations.

These models are used only for Alembic migrations and autogeneration.
The application itself uses asyncpg directly for database operations.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    TIMESTAMP,
    Date,
    BigInteger,
    ForeignKey,
    Table,
)
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

# Base class for all models
Base = declarative_base()


# Association tables for many-to-many relationships
task_assignee = Table(
    "task_assignee",
    Base.metadata,
    Column("task_id", Integer, ForeignKey("task.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    Column("assigned_at", TIMESTAMP, server_default=func.now(), nullable=False),
)

task_tag = Table(
    "task_tag",
    Base.metadata,
    Column("task_id", Integer, ForeignKey("task.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    """User model."""

    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    last_login = Column(TIMESTAMP, nullable=True)

    # Relationships (for Alembic autogeneration)
    created_tasks = relationship("Task", back_populates="creator", foreign_keys="Task.creator_id")
    assigned_tasks = relationship("Task", secondary=task_assignee, back_populates="assignees")
    auth_sessions = relationship("AuthSession", back_populates="user", cascade="all, delete-orphan")


class AuthSession(Base):
    """Authentication session model."""

    __tablename__ = "auth_session"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    expires_at = Column(TIMESTAMP, nullable=False)

    # Relationships
    user = relationship("User", back_populates="auth_sessions")


class TaskStatus(Base):
    """Task status dictionary."""

    __tablename__ = "task_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)

    # Relationships
    tasks = relationship("Task", back_populates="status")


class Tag(Base):
    """Tag model."""

    __tablename__ = "tag"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)

    # Relationships
    tasks = relationship("Task", secondary=task_tag, back_populates="tags")


class Task(Base):
    """Task model."""

    __tablename__ = "task"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status_id = Column(Integer, ForeignKey("task_status.id", ondelete="RESTRICT"), nullable=False)
    creator_id = Column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    deadline_start = Column(Date, nullable=True)
    deadline_end = Column(Date, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    status = relationship("TaskStatus", back_populates="tasks")
    creator = relationship("User", back_populates="created_tasks", foreign_keys=[creator_id])
    assignees = relationship("User", secondary=task_assignee, back_populates="assigned_tasks")
    tags = relationship("Tag", secondary=task_tag, back_populates="tasks")
    attachments = relationship("Attachment", back_populates="task", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="task", cascade="all, delete-orphan")


class Attachment(Base):
    """Attachment model."""

    __tablename__ = "attachment"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("task.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=True)
    storage_path = Column(Text, nullable=False)
    size_bytes = Column(BigInteger, nullable=True)
    uploaded_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

    # Relationships
    task = relationship("Task", back_populates="attachments")

class Comment(Base):
    """Comment model."""
    __tablename__ = "comment"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("task.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())

    #Relationship
    task = relationship("Task", back_populates="comments")


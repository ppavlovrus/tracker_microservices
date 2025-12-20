from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    TIMESTAMP,
    Date,
    ForeignKey,
    Table,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

task_tag = Table(
    "task_tag",
    Base.metadata,
    Column("task_id", Integer, ForeignKey("task.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)

class TaskStatus(Base):
    __tablename__ = "task_status"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)
    tasks = relationship("Task", back_populates="status")

class Task(Base):
    __tablename__ = "task"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status_id = Column(Integer, ForeignKey("task_status.id", ondelete="RESTRICT"), nullable=False)
    creator_id = Column(Integer, nullable=False)
    deadline_start = Column(Date, nullable=True)
    deadline_end = Column(Date, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    status = relationship("TaskStatus", back_populates="tasks")
    tags = relationship("Tag", secondary=task_tag, back_populates="tasks")

class Tag(Base):
    __tablename__ = "tag"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    tasks = relationship("Task", secondary=task_tag, back_populates="tags")
from enum import StrEnum


class Queue(StrEnum):
    TASKS = "tasks.commands"
    TAGS = "tags.commands"
    COMMENTS = "comments.commands"
    ATTACHMENTS = "attachments.commands"
    USERS = "users.commands"

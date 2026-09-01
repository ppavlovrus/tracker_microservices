"""Where the layers are assembled.

Every dependency here reads from ``app.state``, which the lifespan fills once
at startup. Routers ask for what they need instead of reaching for a
module-level global, so a router can be tested by handing it a different
service rather than by reassigning something in another module.
"""

from typing import Annotated

from fastapi import Depends, Request
from task_tracker_common.messaging import RabbitMQClient

from ..core.exceptions import BusUnavailableError
from ..service.tasks import TaskService
from ..service.users import UserService


def get_tasks_service(request: Request) -> TaskService:
    """Assemble the tasks service for one request.

    Built per request rather than once: it is three attribute reads, and it
    keeps the service free of any assumption that it outlives a request.
    """
    state = request.app.state
    return TaskService(bus=state.tasks_bus, cache=state.cache, events=state.events_hub)


def get_users_service(request: Request) -> UserService:
    """Assemble the users service for one request."""
    return UserService(bus=request.app.state.users_bus)


def get_rabbitmq(request: Request) -> RabbitMQClient:
    """The raw bus client, for the calls that have no contracts yet.

    The tasks client reports an absent connection by itself; this one cannot,
    so the check lives here rather than in every endpoint that asks for it.
    """
    client = request.app.state.rabbitmq
    if client is None:
        raise BusUnavailableError("rabbitmq")
    return client


TasksServiceDep = Annotated[TaskService, Depends(get_tasks_service)]
UsersServiceDep = Annotated[UserService, Depends(get_users_service)]
RabbitMQDep = Annotated[RabbitMQClient, Depends(get_rabbitmq)]

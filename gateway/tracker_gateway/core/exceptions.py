class GatewayError(Exception):
    """Base for everything this gateway raises on purpose."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class BusError(GatewayError):
    """The conversation with a worker itself went wrong."""


class BusUnavailableError(BusError):
    def __init__(self, bus_name: str) -> None:
        self.bus_name = bus_name
        super().__init__(f"Queue with name {bus_name} unavailable")


class BusTimeoutError(BusError):
    def __init__(self, command: str, timeout: float) -> None:
        self.command = command
        self.timeout = timeout
        super().__init__(f"{command} got no answer in {timeout}s")


class BusProtocolError(BusError):
    """A payload we sent, or an answer we got, did not match the contract."""


class TaskNotFoundError(GatewayError):
    def __init__(self, task_id: int | None = None) -> None:
        self.task_id = task_id
        super().__init__(f"Task {task_id} not found" if task_id is not None else "Task not found")


class UpstreamFailureError(GatewayError):
    def __init__(self, command: str) -> None:
        self.command = command
        super().__init__(f"Command {command} failed")

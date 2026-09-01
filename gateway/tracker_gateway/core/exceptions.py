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


class UserNotFoundError(GatewayError):
    def __init__(self, user_id: int | None = None) -> None:
        self.user_id = user_id
        super().__init__(f"User {user_id} not found" if user_id is not None else "User not found")


class EmailTakenError(GatewayError):
    def __init__(self) -> None:
        super().__init__("Email already exists")


class UsernameTakenError(GatewayError):
    def __init__(self) -> None:
        super().__init__("Username already exists")


class InvalidCredentialsError(GatewayError):
    """A login that must not say why it failed.

    One class for both causes -- unknown username and wrong password -- so no
    layer above can accidentally tell them apart and leak which usernames
    exist.
    """

    def __init__(self) -> None:
        super().__init__("Invalid username or password")


class UpstreamFailureError(GatewayError):
    def __init__(self, command: str) -> None:
        self.command = command
        super().__init__(f"Command {command} failed")

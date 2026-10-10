"""The bus call the not-yet-reworked routers share.

Tasks and users reach their workers through a typed client and the domain
errors in ``api/errors.py``. Tags, comments and attachments still exchange
plain dicts, and each used to carry its own copy of this: the same guard, the
same three ``except`` clauses and the same success check, differing only in
the status a failed command maps to.

Worker answers now carry an ``ErrorCode`` wherever the worker could classify
the failure, so the status comes from the answer when there is one and from
the endpoint when there is not. This module goes away with the raw dicts.
"""

import logging
from typing import Any

from fastapi import HTTPException
from task_tracker_common.contracts.responses import ErrorCode

logger = logging.getLogger(__name__)

# What a classified failure means over HTTP. A worker that could not classify
# one sends no code at all, and then the endpoint's own default stands.
STATUS_BY_CODE: dict[str, int] = {
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.CONFLICT: 409,
    ErrorCode.INTERNAL: 500,
}


def require_bus(client: Any) -> None:
    """Refuse the request when there is nobody to ask."""
    if not client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


async def call_worker(
    client: Any,
    *,
    queue: str,
    service: str,
    command: str,
    data: dict[str, Any],
    timeout: float,
    failure_status: int,
    failure_detail: str,
) -> dict[str, Any]:
    """Send one command and return its payload, or raise the HTTP error."""
    require_bus(client)

    try:
        response = await client.call(queue_name=queue, message={"command": command, "data": data}, timeout=timeout)
    except TimeoutError as exc:
        logger.error(f"Timeout waiting for {service} service response")
        raise HTTPException(status_code=504, detail=f"{service} service timeout") from exc
    except Exception as exc:
        logger.error(f"Error in {command}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    if not response.get("success"):
        code = response.get("code")
        status = STATUS_BY_CODE.get(code, failure_status)
        detail = response.get("error", failure_detail)
        logger.warning(f"{service} command {command} failed ({status}): {detail}")
        if code is ErrorCode.INTERNAL:
            # A typed worker puts the driver's words in ``error`` on purpose:
            # they are the operator's half of the story, logged one line up.
            # The client gets the generic line, the way the typed clients
            # hand out nothing else either.
            detail = "Internal server error"
        raise HTTPException(status_code=status, detail=detail)

    return response["data"]

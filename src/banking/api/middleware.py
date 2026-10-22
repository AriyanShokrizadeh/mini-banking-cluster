"""Request IDs and structured HTTP access logging."""

import logging
import re
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from banking.config import Settings

SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}")
logger = logging.getLogger("banking.http")


def _request_id(value: str | None) -> str:
    if value and SAFE_REQUEST_ID.fullmatch(value):
        return value
    return str(uuid4())


def _request_details(request: Request) -> dict[str, str | None]:
    return {
        "action": request.state.action,
        "account_id": request.state.account_id,
        "financial_request_id": request.state.financial_request_id,
    }


def request_logging_middleware(
    settings: Settings,
) -> Callable[[Request, RequestResponseEndpoint], Awaitable[Response]]:
    """Create one HTTP middleware bound to the instance's settings."""

    async def log_request(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = _request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        request.state.action = "unmatched"
        request.state.account_id = None
        request.state.financial_request_id = None

        base_fields = {
            "request_id": request_id,
            "instance": settings.instance_name,
            "client_ip": request.client.host if request.client else None,
        }
        logger.info(
            "request_received",
            extra={
                **base_fields,
                "action": f"{request.method} {request.url.path}",
                "result": "received",
            },
        )

        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_unhandled",
                extra={
                    **base_fields,
                    **_request_details(request),
                    "result": "unhandled_error",
                    "status_code": 500,
                    "latency_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            raise

        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                **base_fields,
                **_request_details(request),
                "result": "success" if response.status_code < 400 else "error",
                "status_code": response.status_code,
                "latency_ms": round((perf_counter() - started_at) * 1000, 3),
            },
        )
        return response

    return log_request

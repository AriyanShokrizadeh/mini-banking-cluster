import logging
from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from banking.domain.exceptions import BankingError
from banking.logging import database_error_fields

logger = logging.getLogger("banking.errors")


def error_response(
    request: Request,
    code: str,
    message: str,
    status_code: int,
) -> JSONResponse:
    request_id = getattr(request.state, "financial_request_id", None) or getattr(
        request.state, "request_id", None
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "request_id": request_id,
            "error": {"code": code, "message": message},
        },
    )


def _capture_validation_context(request: Request, body: object) -> None:
    if not isinstance(body, dict):
        return

    fields = {
        "action": "action",
        "account": "account_id",
        "request_id": "financial_request_id",
    }

    for field, attribute in fields.items():
        if isinstance(value := body.get(field), str):
            setattr(request.state, attribute, value[:64])


def _validation_problem(
    errors: Sequence[Mapping[str, Any]],
) -> tuple[str, str, int]:
    types = {error["type"] for error in errors}
    fields = {field for error in errors for field in error.get("loc", ()) if isinstance(field, str)}

    if "json_invalid" in types:
        return "MALFORMED_REQUEST", "Malformed JSON body", 400

    if "missing" in types:
        return "MISSING_FIELD", "A required field is missing", 422

    if "action" in fields:
        return "UNSUPPORTED_ACTION", "Unsupported banking action", 422

    if "amount" in fields:
        return "INVALID_AMOUNT", "Amount must be a positive integer", 422

    return "INVALID_REQUEST", "Request validation failed", 422


async def on_business_error(request: Request, exc: BankingError) -> JSONResponse:
    return error_response(request, exc.code, str(exc), exc.http_status)


async def on_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    _capture_validation_context(request, exc.body)
    code, message, status_code = _validation_problem(exc.errors())
    return error_response(request, code, message, status_code)


async def on_database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error(
        "database_operation_failed",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            **database_error_fields(exc),
        },
    )
    return error_response(
        request,
        "SERVICE_UNAVAILABLE",
        "Database transaction failed; outcome may be unknown",
        503,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register typed HTTP error handlers without weakening their signatures."""
    app.exception_handler(BankingError)(on_business_error)
    app.exception_handler(RequestValidationError)(on_validation_error)
    app.exception_handler(SQLAlchemyError)(on_database_error)

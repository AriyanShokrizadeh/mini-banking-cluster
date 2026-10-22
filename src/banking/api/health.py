"""Read-only liveness/connectivity and committed-write readiness probes."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from banking.infrastructure.database import check_ysql_connection, probe_committed_write
from banking.logging import database_error_fields

router = APIRouter(tags=["Health"])
logger = logging.getLogger("banking.health")


def get_optional_engine(request: Request) -> Engine | None:
    return getattr(request.app.state, "engine", None)


def _unavailable(status: str, reason: str) -> JSONResponse:
    return JSONResponse(status_code=503, content={"status": status, "reason": reason})


@router.get("/health/live")
def liveness(request: Request) -> dict[str, str]:
    request.state.action = "health_live"
    return {"status": "alive", "instance": request.app.state.settings.instance_name}


@router.get("/health/db", response_model=None)
def database_connectivity(request: Request) -> dict[str, str] | JSONResponse:
    request.state.action = "health_db"
    engine = get_optional_engine(request)
    if engine is None:
        return _unavailable("unavailable", "database_not_configured")

    try:
        check_ysql_connection(engine)
    except Exception as exc:
        logger.error("database_connectivity_probe_failed", extra=database_error_fields(exc))
        return _unavailable("unavailable", "database_unreachable")

    return {"status": "connected", "capability": "read_only_probe"}


@router.get("/health/ready", response_model=None)
def readiness(request: Request) -> dict[str, str] | JSONResponse:
    request.state.action = "health_ready"
    engine = get_optional_engine(request)
    if engine is None:
        return _unavailable("not_ready", "database_not_configured")

    try:
        probe_committed_write(engine, request.app.state.settings.instance_name)
    except Exception as exc:
        logger.error("database_readiness_probe_failed", extra=database_error_fields(exc))
        return _unavailable("not_ready", "database_write_unavailable")

    return {
        "status": "ready",
        "instance": request.app.state.settings.instance_name,
        "capability": "committed_write_probe",
    }

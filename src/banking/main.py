"""FastAPI application factory and lifecycle management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from banking.api.banking import router as banking_router
from banking.api.errors import register_exception_handlers
from banking.api.health import router as health_router
from banking.api.middleware import request_logging_middleware
from banking.config import Settings, get_settings
from banking.infrastructure.database import make_engine
from banking.logging import configure_logging


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
) -> FastAPI:
    """Create the banking API without modifying the database schema."""
    config = settings if settings is not None else get_settings()
    configure_logging(config.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        """Manage only the database engine created by this application."""
        created_engine = (
            make_engine(config) if engine is None and config.database_url is not None else None
        )
        application.state.engine = engine if engine is not None else created_engine

        try:
            yield
        finally:
            if created_engine is not None:
                created_engine.dispose()

    app = FastAPI(
        title=config.app_name,
        version="0.7.0",
        description="Transactional banking API backed by YugabyteDB/YSQL",
        lifespan=lifespan,
    )

    app.state.settings = config
    app.middleware("http")(request_logging_middleware(config))
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(banking_router)

    return app


app = create_app()

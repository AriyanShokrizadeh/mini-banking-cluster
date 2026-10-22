"""Use `python -m banking` to start one Uvicorn worker per banking VM."""

import uvicorn

from banking.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "banking.main:app",
        host=settings.host,
        port=settings.port,
        workers=1,
        limit_concurrency=settings.max_concurrent_requests,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()

"""Run Vishnu's authenticated local web/PWA surface without the desktop shell."""

import uvicorn

from core.config import settings


def main() -> None:
    uvicorn.run(
        "server.cloud_app:app",
        host=settings.control_server_host,
        port=settings.control_server_port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()

"""Command-line entry point: ``jarvis-core`` or ``python -m jarvis_core``."""

from __future__ import annotations

import uvicorn

from jarvis_core.api.app import create_app
from jarvis_core.config import Settings
from jarvis_core.logging import configure_logging


def main() -> None:
    """Load settings, configure logging and serve the API with uvicorn."""
    settings = Settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        ws_max_size=4 * 1024 * 1024,
    )


if __name__ == "__main__":
    main()

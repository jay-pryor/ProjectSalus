"""Uvicorn entry point for the Salus Interface API.

Used by the ``salus interface`` CLI command and in integration tests.
"""

from __future__ import annotations

import uvicorn

from salus.interface_api.app import app


def run(host: str = "127.0.0.1", port: int = 5000, log_level: str = "info") -> None:
    """Start the uvicorn server.

    Args:
        host: Bind address.  Defaults to ``127.0.0.1`` (localhost only).
        port: TCP port to listen on.
        log_level: Uvicorn log level string (``"info"``, ``"debug"``, etc.).
    """
    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    run()

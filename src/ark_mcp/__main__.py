"""Entry point for ``python -m ark_mcp``.

Reads transport settings from the environment and calls ``mcp.run()``.
Use ``fastmcp run src/ark_mcp/server.py:mcp`` for the standard CLI.

On macOS, injects ``truststore`` so Python uses the system Keychain for
TLS certificate verification (required for BytePlus API hosts).
"""

from __future__ import annotations

from contextlib import suppress

import truststore

truststore.inject_into_ssl()

from ark_mcp.config.env import get_settings  # noqa: E402
from ark_mcp.observability.logger import info as log_info  # noqa: E402
from ark_mcp.server import mcp  # noqa: E402


def main() -> None:
    settings = get_settings()

    if settings.mcp_transport == "http":
        log_info(
            "server_starting",
            transport="http",
            host=settings.mcp_host,
            port=settings.mcp_port,
        )
        mcp.run(
            transport="http",
            host=settings.mcp_host,
            port=settings.mcp_port,
            host_origin_protection=True,
            allowed_hosts=settings.allowed_hosts,
            allowed_origins=settings.allowed_origins,
            stateless_http=True,
            uvicorn_config={
                "timeout_graceful_shutdown": int(settings.request_timeout_ms / 1000),
            },
        )
    else:
        log_info("server_starting", transport="stdio")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    # FastMCP/Uvicorn complete graceful shutdown before propagating Ctrl-C.
    with suppress(KeyboardInterrupt):
        main()
    log_info("server_stopped")

"""Entry point for ``python -m modelark_mcp``.

Reads transport settings from the environment and calls ``mcp.run()``.
Use ``fastmcp run src/modelark_mcp/server.py:mcp`` for the standard CLI.

On macOS, injects ``truststore`` so Python uses the system Keychain for
TLS certificate verification (required for BytePlus API hosts).
"""

from __future__ import annotations

import truststore

truststore.inject_into_ssl()

from modelark_mcp.config.env import get_settings  # noqa: E402
from modelark_mcp.server import mcp  # noqa: E402


def main() -> None:
    settings = get_settings()

    if settings.mcp_transport == "http":
        mcp.run(
            transport="http",
            host=settings.mcp_host,
            port=settings.mcp_port,
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

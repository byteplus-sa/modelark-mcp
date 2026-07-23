#!/usr/bin/env bash

# Audit the locked third-party dependency set. The project itself is not
# published to PyPI, so passing the active environment directly to pip-audit
# would make strict mode fail while trying to resolve modelark-mcp.
set -euo pipefail

requirements_file="$(mktemp "${TMPDIR:-/tmp}/modelark-mcp-audit.XXXXXX")"
trap 'rm -f "$requirements_file"' EXIT

uv export --quiet --locked --no-emit-project --format requirements-txt --output-file "$requirements_file"
uv run pip-audit --strict --requirement "$requirements_file"

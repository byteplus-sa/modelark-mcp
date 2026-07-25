#!/usr/bin/env bash

# Audit the locked third-party dependency set. The project itself is not
# published to PyPI, so passing the active environment directly to pip-audit
# would make strict mode fail while trying to resolve modelark-mcp.
set -euo pipefail

requirements_file="$(mktemp "${TMPDIR:-/tmp}/modelark-mcp-audit.XXXXXX")"
# sitecustomize.py is auto-imported by the Python interpreter at startup, so
# injecting truststore here lets pip-audit reach PyPI/OSV over the OS trust
# store (macOS Keychain / Windows cert store / Linux ca-certificates). This
# matters in corporate or MITM-proxy environments where certifi's bundled
# Mozilla roots are insufficient and pip-audit otherwise fails with
# SSLCertVerificationError. Falls back silently if truststore is unavailable.
sitecustomize_dir="$(mktemp -d "${TMPDIR:-/tmp}/modelark-mcp-audit-site.XXXXXX")"
trap 'rm -f "$requirements_file"; rm -rf "$sitecustomize_dir"' EXIT

cat > "$sitecustomize_dir/sitecustomize.py" <<'PY'
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass
PY

uv export --quiet --locked --no-emit-project --format requirements-txt --output-file "$requirements_file"
PYTHONPATH="$sitecustomize_dir${PYTHONPATH:+:$PYTHONPATH}" uv run pip-audit --strict --requirement "$requirements_file"

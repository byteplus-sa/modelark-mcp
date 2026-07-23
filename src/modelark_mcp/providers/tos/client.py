"""BytePlus TOS gateway — object upload and presigned URL generation.

Wraps the synchronous ``tos`` Python SDK (``TosClientV2``) behind
async-friendly methods using ``asyncio.to_thread``. The SDK handles
TOS4-HMAC-SHA256 request signing; this gateway adds error normalization
and structured logging.

TOS credentials are startup configuration (``TOS_ACCESS_KEY`` /
``TOS_SECRET_KEY``) and never tool arguments, matching the existing
provider-credential convention.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, cast

import tos
from tos.enum import HttpMethodType
from tos.exceptions import TosClientError, TosServerError

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError, ProviderName
from modelark_mcp.observability.logger import info as log_info

PROVIDER: ProviderName = "tos"


class TosGateway:
    """BytePlus TOS gateway wrapping the ``tos`` SDK.

    The underlying ``TosClientV2`` is synchronous; every SDK call is dispatched
    via ``asyncio.to_thread`` so the event loop is never blocked.  SDK
    exceptions (``TosServerError`` / ``TosClientError``) are normalized to
    ``ProviderError`` so the retry policy and error-result helpers work
    uniformly across all providers.
    """

    def __init__(
        self,
        *,
        client: Any = None,
        bucket: str | None = None,
        presign_ttl: int | None = None,
    ) -> None:
        settings = get_settings()
        self._bucket = bucket if bucket is not None else settings.tos_bucket
        self._presign_ttl = (
            presign_ttl if presign_ttl is not None else settings.tos_presign_ttl_seconds
        )
        self._client: Any = client or tos.TosClientV2(
            ak=settings.tos_access_key,
            sk=settings.tos_secret_key,
            endpoint=settings.tos_endpoint,
            region=settings.tos_region,
            security_token=settings.tos_security_token or None,
        )

    async def upload_bytes(self, *, key: str, data: bytes, mime_type: str) -> None:
        """Upload raw bytes to TOS via ``put_object``."""

        def _upload() -> None:
            output = self._client.put_object(
                bucket=self._bucket,
                key=key,
                content=data,
                content_type=mime_type,
            )
            request_id = getattr(output, "request_id", None)
            log_info("tos_upload", key=key, request_id=request_id, bytes=len(data))

        await self._dispatch(_upload, operation="upload")

    async def upload_file(self, *, key: str, file_path: str, mime_type: str) -> None:
        """Upload a local file to TOS via ``put_object_from_file``.

        Streams the file without loading it fully into memory.
        """

        def _upload() -> None:
            output = self._client.put_object_from_file(
                bucket=self._bucket,
                key=key,
                file_path=file_path,
                content_type=mime_type,
            )
            request_id = getattr(output, "request_id", None)
            log_info("tos_upload_file", key=key, file_path=file_path, request_id=request_id)

        await self._dispatch(_upload, operation="upload_file")

    async def presign_get(self, *, key: str, expires: int | None = None) -> str:
        """Generate a presigned HTTPS GET URL for an object."""
        ttl = expires or self._presign_ttl

        def _presign() -> str:
            return str(
                self._client.pre_signed_url(
                    HttpMethodType.Http_Method_Get,
                    bucket=self._bucket,
                    key=key,
                    expires=ttl,
                )
            )

        return cast("str", await self._dispatch(_presign, operation="presign"))

    async def close(self) -> None:
        client = self._client
        self._client = None
        close = getattr(client, "close", None)
        if not callable(close):
            return
        with contextlib.suppress(Exception):
            await asyncio.to_thread(close)

    async def _dispatch(self, func: Any, *, operation: str) -> Any:
        try:
            return await asyncio.to_thread(func)
        except TosServerError as exc:
            raise _normalize_server_error(exc, operation) from None
        except TosClientError as exc:
            raise _normalize_client_error(exc, operation) from None
        except Exception as exc:
            raise _normalize_unknown_error(exc, operation) from None


def _normalize_server_error(exc: TosServerError, operation: str) -> ProviderError:
    status = getattr(exc, "status_code", None) or 0
    code = getattr(exc, "code", None) or "TOS_SERVER_ERROR"
    message = getattr(exc, "message", None) or str(exc)
    request_id = getattr(exc, "request_id", None)
    retryable = status >= 500 or status == 429
    return ProviderError(
        NormalizedProviderError(
            provider=PROVIDER,
            operation=operation,
            http_status=status or None,
            code=code,
            message=f"TOS {operation} failed: {message}",
            request_id=request_id,
            retryable=retryable,
        )
    )


def _normalize_client_error(exc: TosClientError, operation: str) -> ProviderError:
    message = getattr(exc, "message", None) or str(exc)
    return ProviderError(
        NormalizedProviderError(
            provider=PROVIDER,
            operation=operation,
            http_status=None,
            code="TOS_CLIENT_ERROR",
            message=f"TOS {operation} client error: {message}",
            request_id=None,
            retryable=True,
        )
    )


def _normalize_unknown_error(exc: Exception, operation: str) -> ProviderError:
    return ProviderError(
        NormalizedProviderError(
            provider=PROVIDER,
            operation=operation,
            http_status=None,
            code="TOS_UNKNOWN_ERROR",
            message=f"TOS {operation} failed with unexpected error: {exc}",
            request_id=None,
            retryable=True,
        )
    )

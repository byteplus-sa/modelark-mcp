"""Amazon S3 (and S3-compatible) gateway — object upload + presigned URLs.

Wraps the synchronous ``boto3`` S3 client behind async-friendly methods using
``asyncio.to_thread``, mirroring ``TosGateway``. ``botocore.exceptions.
ClientError`` is normalized to ``ProviderError`` so retry policy and error
helpers work uniformly across all object-storage backends.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, cast

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError, ProviderName
from modelark_mcp.observability.logger import info as log_info

PROVIDER: ProviderName = "s3"


class S3Gateway:
    """Amazon S3 gateway wrapping ``boto3.client('s3', ...)``."""

    def __init__(
        self,
        *,
        client: Any = None,
        bucket: str | None = None,
        presign_ttl: int | None = None,
    ) -> None:
        settings = get_settings()
        self._bucket = bucket if bucket is not None else settings.s3_bucket
        self._presign_ttl = (
            presign_ttl if presign_ttl is not None else settings.s3_presign_ttl_seconds
        )
        self._client: Any = client or boto3.client(
            "s3",
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint or None,
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"} if settings.s3_endpoint else {},
            ),
        )

    async def upload_bytes(self, *, key: str, data: bytes, mime_type: str) -> None:
        def _upload() -> None:
            response = self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=mime_type,
            )
            request_id = (
                (response.get("ResponseMetadata", {}) or {}).get("RequestId")
                if isinstance(response, dict)
                else None
            )
            log_info("s3_upload", key=key, bytes=len(data), request_id=request_id)

        await self._dispatch(_upload, operation="upload")

    async def upload_file(self, *, key: str, file_path: str, mime_type: str) -> None:
        def _upload() -> None:
            self._client.upload_file(
                Filename=file_path,
                Bucket=self._bucket,
                Key=key,
                ExtraArgs={"ContentType": mime_type},
            )
            log_info("s3_upload_file", key=key, file_path=file_path)

        await self._dispatch(_upload, operation="upload_file")

    async def presign_get(self, *, key: str, expires: int | None = None) -> str:
        ttl = expires or self._presign_ttl

        def _presign() -> str:
            return str(
                self._client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket, "Key": key},
                    ExpiresIn=ttl,
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
        except ClientError as exc:
            raise _normalize_client_error(exc, operation) from None
        except Exception as exc:
            raise _normalize_unknown_error(exc, operation) from None


def _normalize_client_error(exc: ClientError, operation: str) -> ProviderError:
    response = getattr(exc, "response", {}) or {}
    error = response.get("Error", {}) or {}
    metadata = response.get("ResponseMetadata", {}) or {}
    code = error.get("Code") or "S3_CLIENT_ERROR"
    message = error.get("Message") or str(exc)
    status = metadata.get("HTTPStatusCode")
    retryable = status is None or status >= 500 or status == 429
    return ProviderError(
        NormalizedProviderError(
            provider=PROVIDER,
            operation=operation,
            http_status=status,
            code=code,
            message=f"S3 {operation} failed: {message}",
            request_id=metadata.get("RequestId"),
            retryable=retryable,
        )
    )


def _normalize_unknown_error(exc: Exception, operation: str) -> ProviderError:
    return ProviderError(
        NormalizedProviderError(
            provider=PROVIDER,
            operation=operation,
            http_status=None,
            code="S3_UNKNOWN_ERROR",
            message=f"S3 {operation} failed with unexpected error: {exc}",
            request_id=None,
            retryable=True,
        )
    )

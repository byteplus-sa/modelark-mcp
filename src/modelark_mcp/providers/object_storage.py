"""Object-storage gateway protocol and backend factory.

Both BytePlus TOS (``tos`` SDK) and Amazon S3 (``boto3``) implement this
protocol. Tools program to the protocol; the active backend is selected by
``OBJECT_STORAGE_BACKEND`` at startup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from modelark_mcp.config.env import Settings


@runtime_checkable
class ObjectStorageGateway(Protocol):
    """Protocol for object-storage upload and presigned-URL backends.

    Both ``TosGateway`` and ``S3Gateway`` conform. SDK calls are dispatched
    via ``asyncio.to_thread``; all methods raise ``ProviderError`` on
    failure, normalized with ``retryable``/``http_status`` for uniform
    retry handling via ``call_with_retry``.
    """

    async def upload_bytes(
        self,
        *,
        key: str,
        data: bytes,
        mime_type: str,
    ) -> None:
        """Upload raw bytes. Raises ``ProviderError`` on SDK failure."""
        ...

    async def upload_file(
        self,
        *,
        key: str,
        file_path: str,
        mime_type: str,
    ) -> None:
        """Upload a local file (streamed, not loaded into memory).

        Raises ``ProviderError`` on SDK failure.
        """
        ...

    async def presign_get(
        self,
        *,
        key: str,
        expires: int | None = None,
    ) -> str:
        """Return a presigned HTTPS GET URL for the object.

        ``expires`` overrides the backend default TTL when provided.
        Raises ``ProviderError`` on SDK failure.
        """
        ...

    async def close(self) -> None:
        """Release SDK client resources. Idempotent; safe to call in ``finally``."""
        ...


def make_object_storage_gateway(settings: Settings | None = None) -> ObjectStorageGateway:
    """Return the configured object-storage gateway (tos or s3)."""
    from modelark_mcp.config.env import get_settings

    settings = settings or get_settings()
    if settings.object_storage_backend == "s3":
        if not settings.has_s3:
            raise ValueError(
                "S3 object storage selected but S3 credentials are not configured. "
                "Set S3_ACCESS_KEY, S3_SECRET_KEY, and S3_BUCKET."
            )
        from modelark_mcp.providers.s3.client import S3Gateway

        return S3Gateway()
    if not settings.has_tos:
        raise ValueError(
            "TOS object storage selected but TOS credentials are not configured. "
            "Set TOS_ACCESS_KEY, TOS_SECRET_KEY, and TOS_BUCKET."
        )
    from modelark_mcp.providers.tos.client import TosGateway

    return TosGateway()

"""Protocol conformance tests for ObjectStorageGateway.

Asserts that both ``TosGateway`` and ``S3Gateway`` structurally satisfy the
``ObjectStorageGateway`` protocol via ``isinstance`` (possible because the
protocol is ``@runtime_checkable``). Without this, a method rename on
``TosGateway`` would silently break the protocol at runtime.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from modelark_mcp.providers.object_storage import ObjectStorageGateway
from modelark_mcp.providers.s3.client import S3Gateway
from modelark_mcp.providers.tos.client import TosGateway


def _mock_tos_client() -> MagicMock:
    client = MagicMock()
    client.put_object.return_value = MagicMock(request_id="req-tos")
    client.put_object_from_file.return_value = MagicMock(request_id="req-tos")
    client.pre_signed_url.return_value = "https://tos.example.com/url"
    client.close = MagicMock()
    return client


def _mock_s3_client() -> MagicMock:
    client = MagicMock()
    client.put_object.return_value = {"ResponseMetadata": {"RequestId": "req-s3"}}
    client.upload_file.return_value = None
    client.generate_presigned_url.return_value = "https://s3.example.com/url"
    client.close = MagicMock()
    return client


class TestProtocolConformance:
    @pytest.mark.parametrize(
        ("cls", "client_factory"),
        [
            (TosGateway, _mock_tos_client),
            (S3Gateway, _mock_s3_client),
        ],
    )
    def test_conforms_to_protocol(self, cls, client_factory) -> None:
        gateway = cls(client=client_factory(), bucket="test", presign_ttl=3600)
        assert isinstance(gateway, ObjectStorageGateway)

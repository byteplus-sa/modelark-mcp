"""Unit tests for URL security policy (SSRF prevention)."""

from __future__ import annotations

import pytest

from modelark_mcp.security.url_policy import UrlValidationError, validate_url


class TestUrlValidation:
    """Tests for the URL SSRF policy."""

    def test_https_url_accepted(self) -> None:
        validate_url("https://example.com/image.png")

    def test_http_url_rejected(self) -> None:
        with pytest.raises(UrlValidationError, match="HTTP URLs are not allowed"):
            validate_url("http://example.com/image.png")

    def test_http_url_allowed_with_flag(self) -> None:
        validate_url("http://example.com/image.png", allow_http=True)

    def test_file_scheme_rejected(self) -> None:
        with pytest.raises(UrlValidationError, match="scheme"):
            validate_url("file:///etc/passwd")

    def test_missing_hostname_rejected(self) -> None:
        with pytest.raises(UrlValidationError, match="hostname"):
            validate_url("https://")

    def test_aws_metadata_host_blocked(self) -> None:
        with pytest.raises(UrlValidationError, match="blocked"):
            validate_url("https://169.254.169.254/latest/meta-data/")

    def test_gcp_metadata_host_blocked(self) -> None:
        with pytest.raises(UrlValidationError, match="blocked"):
            validate_url("https://metadata.google.internal/computeMetadata/v1/")

    def test_loopback_ip_blocked(self) -> None:
        with pytest.raises(UrlValidationError, match="blocked IP"):
            validate_url("https://127.0.0.1/image.png")

    def test_private_ip_blocked(self) -> None:
        with pytest.raises(UrlValidationError, match="blocked IP"):
            validate_url("https://10.0.0.1/image.png")

    def test_link_local_blocked(self) -> None:
        with pytest.raises(UrlValidationError, match="blocked IP"):
            validate_url("https://169.254.1.1/image.png")

    def test_multicast_blocked(self) -> None:
        with pytest.raises(UrlValidationError, match="blocked IP"):
            validate_url("https://224.0.0.1/image.png")

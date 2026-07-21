"""Unit tests for model capability registry."""

from __future__ import annotations

import pytest

from modelark_mcp.config.model_capabilities import (
    ImageCapabilities,
    ModelFamily,
    VideoCapabilities,
    get_capability_registry,
)


class TestCapabilityRegistry:
    """Tests for the model capability registry."""

    def test_get_default_image_capabilities(self) -> None:
        registry = get_capability_registry()
        caps = registry.get_image_capabilities()
        assert isinstance(caps, ImageCapabilities)
        assert caps.family in (
            ModelFamily.SEEDREAM_PRO,
            ModelFamily.SEEDREAM_LITE,
            ModelFamily.SEEDREAM_4X,
        )

    def test_get_default_video_capabilities(self) -> None:
        registry = get_capability_registry()
        caps = registry.get_video_capabilities()
        assert isinstance(caps, VideoCapabilities)
        assert caps.family in (
            ModelFamily.SEEDANCE_2,
            ModelFamily.SEEDANCE_2_FAST,
            ModelFamily.SEEDANCE_2_MINI,
        )

    def test_invalid_image_model_raises(self) -> None:
        registry = get_capability_registry()
        with pytest.raises(ValueError, match="not in the configured"):
            registry.get_image_capabilities("nonexistent-model")

    def test_invalid_video_model_raises(self) -> None:
        registry = get_capability_registry()
        with pytest.raises(ValueError, match="not in the configured"):
            registry.get_video_capabilities("nonexistent-model")

    def test_validate_output_format_valid(self) -> None:
        registry = get_capability_registry()
        caps = registry.get_image_capabilities()
        if "png" in caps.supported_output_formats:
            assert registry.validate_output_format(None, "png") == "png"

    def test_validate_output_format_invalid_raises(self) -> None:
        registry = get_capability_registry()
        with pytest.raises(ValueError, match="not supported"):
            registry.validate_output_format(None, "gif")

    def test_validate_resolution_valid(self) -> None:
        registry = get_capability_registry()
        caps = registry.get_video_capabilities()
        if caps.supported_resolutions:
            res = caps.supported_resolutions[0]
            assert registry.validate_resolution(None, res) == res

    def test_validate_resolution_invalid_raises(self) -> None:
        registry = get_capability_registry()
        with pytest.raises(ValueError, match="not supported"):
            registry.validate_resolution(None, "9999p")

    def test_validate_duration_auto(self) -> None:
        registry = get_capability_registry()
        assert registry.validate_duration(None, -1) == -1

    def test_validate_duration_in_range(self) -> None:
        registry = get_capability_registry()
        assert registry.validate_duration(None, 5) == 5

    def test_validate_duration_out_of_range_raises(self) -> None:
        registry = get_capability_registry()
        with pytest.raises(ValueError, match="outside the supported range"):
            registry.validate_duration(None, 100)

    def test_list_image_models(self) -> None:
        registry = get_capability_registry()
        models = registry.list_image_models()
        assert len(models) >= 1

    def test_list_video_models(self) -> None:
        registry = get_capability_registry()
        models = registry.list_video_models()
        assert len(models) >= 1

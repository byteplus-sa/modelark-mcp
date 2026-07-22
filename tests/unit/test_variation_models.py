"""Unit tests for VariationResult and VariationSummary models."""

from __future__ import annotations

from modelark_mcp.domain.artifacts import ArtifactRef
from modelark_mcp.domain.models import VariationResult, VariationSummary


class TestVariationResult:
    """Tests for VariationResult."""

    def test_minimal_success(self) -> None:
        r = VariationResult(index=0)
        assert r.index == 0
        assert r.artifact is None
        assert r.task_id is None
        assert r.error is None
        assert r.seed is None

    def test_with_artifact(self) -> None:
        artifact = ArtifactRef(
            id="abc",
            uri="seed-media://artifacts/abc",
            media_type="image",
            mime_type="image/png",
            created_at="2026-01-01T00:00:00Z",
        )
        r = VariationResult(index=1, seed=42, artifact=artifact)
        assert r.artifact is not None
        assert r.artifact.id == "abc"
        assert r.seed == 42

    def test_with_task_id(self) -> None:
        r = VariationResult(index=0, task_id="cgt-123")
        assert r.task_id == "cgt-123"
        assert r.artifact is None

    def test_with_error(self) -> None:
        r = VariationResult(
            index=2,
            error={"code": "TIMEOUT", "message": "timed out"},
        )
        assert r.error is not None
        assert r.error["code"] == "TIMEOUT"


class TestVariationSummary:
    """Tests for VariationSummary."""

    def test_all_succeeded(self) -> None:
        results = [VariationResult(index=i) for i in range(3)]
        s = VariationSummary(total=3, succeeded=3, failed=0, variations=results)
        assert s.total == 3
        assert s.succeeded == 3
        assert s.failed == 0
        assert len(s.variations) == 3

    def test_partial_failure(self) -> None:
        results = [
            VariationResult(index=0),
            VariationResult(index=1, error={"code": "FAIL"}),
            VariationResult(index=2),
        ]
        s = VariationSummary(total=3, succeeded=2, failed=1, variations=results)
        assert s.succeeded == 2
        assert s.failed == 1

    def test_empty(self) -> None:
        s = VariationSummary(total=0, succeeded=0, failed=0, variations=[])
        assert s.total == 0
        assert len(s.variations) == 0

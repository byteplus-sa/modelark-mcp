"""Tests for optional background-task execution guards."""

from __future__ import annotations

from modelark_mcp.tools._task_execution import persistence_requires_task
from tests.fixtures.fake_context import FakeContext


def test_persistence_requires_task_for_foreground_context() -> None:
    context = FakeContext(task_id=None)

    result = persistence_requires_task(context, persist_output=True)

    assert result is not None
    assert result.is_error is True
    assert "task-augmented execution" in str(result.content)


def test_foreground_status_polling_allows_persistence_disabled() -> None:
    context = FakeContext(task_id=None)

    assert persistence_requires_task(context, persist_output=False) is None


def test_empty_task_identifier_is_not_task_augmented() -> None:
    context = FakeContext(task_id="")

    result = persistence_requires_task(context, persist_output=True)

    assert result is not None
    assert result.is_error is True


def test_task_augmented_persistence_is_allowed() -> None:
    context = FakeContext(task_id="task-123")

    assert persistence_requires_task(context, persist_output=True) is None

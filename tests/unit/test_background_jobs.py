from __future__ import annotations

from inspect import signature

from fastmcp_tasks.creation import create_task
from fastmcp_tasks.handlers import tasks_cancel, tasks_get

from ark_mcp.background_jobs import (
    BACKGROUND_TOOL_SPECS,
    optional_background_tool_names,
    required_background_tool_names,
)


def test_background_tool_registry_modes_partition_all_targets() -> None:
    required = required_background_tool_names()
    optional = optional_background_tool_names()

    assert required
    assert optional
    assert len(required) == 19
    assert len(optional) == 8
    assert required.isdisjoint(optional)
    assert required | optional == BACKGROUND_TOOL_SPECS.keys()


def test_fastmcp_task_adapter_contract_matches_pinned_minor() -> None:
    assert tuple(signature(create_task).parameters) == ("tool", "arguments", "context")
    assert tuple(signature(tasks_get).parameters) == ("server", "task_id")
    assert tuple(signature(tasks_cancel).parameters) == ("server", "task_id")

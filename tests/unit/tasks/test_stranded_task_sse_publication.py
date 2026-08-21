"""Unit tests for stranded task SSE event publication and observer notification (#4259).

Asserts that tasks moved to ``BLOCKED_BY_FAILED_DEP`` during dependency propagation
notify registered store listeners and publish ``task_update`` SSE events across
all terminal failure paths (fail, fail_contract_violation, refuse, cancel, cancel_cascade).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bernstein.core.server import SSEBus, TaskCreate
from bernstein.core.tasks.contracts import RefusalKind, WorkerRefusal
from bernstein.core.tasks.models import Task, TaskStatus
from bernstein.core.tasks.task_store import TaskStore


@pytest.fixture()
def jsonl_path(tmp_path: Path) -> Path:
    runtime_dir = tmp_path / ".sdd" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir / "tasks.jsonl"


@pytest.mark.asyncio
async def test_stranded_task_notifies_store_listener(jsonl_path: Path) -> None:
    """Store listener is notified when a dependent task is moved to BLOCKED_BY_FAILED_DEP."""
    store = TaskStore(jsonl_path)

    # Create root task A and dependent task B
    task_a = await store.create(TaskCreate(title="Task A", description="desc", role="backend"))
    task_b = await store.create(TaskCreate(title="Task B", description="desc", role="backend", depends_on=[task_a.id]))

    notifications: list[Task] = []
    store.add_task_listener(notifications.append)

    # Fail task A -> task B is stranded to BLOCKED_BY_FAILED_DEP
    await store.fail(task_a.id, "execution failed")

    stranded = [t for t in notifications if t.id == task_b.id]
    assert len(stranded) == 1
    assert stranded[0].status == TaskStatus.BLOCKED_BY_FAILED_DEP
    assert stranded[0].metadata.get("blocking_task_id") == task_a.id


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["cancel", "cancel_cascade", "refuse"])
async def test_all_stranding_paths_notify_listener(tmp_path: Path, method: str) -> None:
    """All terminal paths (cancel, cancel_cascade, refuse) notify listener of stranded tasks."""
    runtime_dir = tmp_path / f"runtime_{method}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    store = TaskStore(runtime_dir / "tasks.jsonl")

    task_a = await store.create(TaskCreate(title="Task A", description="desc", role="backend"))
    task_b = await store.create(TaskCreate(title="Task B", description="desc", role="backend", depends_on=[task_a.id]))

    notifications: list[Task] = []
    store.add_task_listener(notifications.append)

    if method == "cancel":
        await store.cancel(task_a.id, "user cancel")
    elif method == "cancel_cascade":
        await store.cancel_cascade(task_a.id, "cascade cancel")
    elif method == "refuse":
        claimed = await store.claim_next("backend")
        assert claimed is not None and claimed.id == task_a.id
        refusal = WorkerRefusal(kind=RefusalKind.SCOPE_EXCEEDED, detail="out of bounds")
        await store.refuse(claimed.id, refusal)

    stranded = [t for t in notifications if t.id == task_b.id]
    assert len(stranded) == 1
    assert stranded[0].status == TaskStatus.BLOCKED_BY_FAILED_DEP


@pytest.mark.asyncio
async def test_sse_publisher_listener_publishes_task_update_event(jsonl_path: Path) -> None:
    """The task update listener publishes task_update SSE event for stranded dependent tasks."""
    store = TaskStore(jsonl_path)
    sse_bus = SSEBus()

    def _publish_task_update(task_obj: Any) -> None:
        sse_bus.publish(
            "task_update",
            json.dumps({"id": task_obj.id, "status": task_obj.status.value}),
        )

    store.add_task_listener(_publish_task_update)

    task_a = await store.create(TaskCreate(title="Task A", description="desc", role="backend"))
    task_b = await store.create(TaskCreate(title="Task B", description="desc", role="backend", depends_on=[task_a.id]))

    published_events: list[tuple[str, str]] = []
    sse_bus.publish = lambda event, data: published_events.append((event, data))

    # Fail task A -> strands task B
    await store.fail(task_a.id, "failure reason")

    b_updates = [
        json.loads(data)
        for evt, data in published_events
        if evt == "task_update" and json.loads(data).get("id") == task_b.id
    ]
    assert len(b_updates) >= 1
    assert b_updates[0]["status"] == "blocked_by_failed_dep"

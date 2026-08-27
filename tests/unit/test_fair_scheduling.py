"""Tests for fair scheduling across priorities."""

from __future__ import annotations

import time

import pytest
from bernstein.core.models import Task
from bernstein.core.tick_pipeline import group_by_role


@pytest.fixture()
def sample_tasks() -> list[Task]:
    """Create sample tasks with different priorities and ages."""
    current_time = time.time()
    return [
        # P1 tasks (critical) - just created
        Task(
            id="p1-task-1",
            title="Critical bug fix 1",
            description="Fix critical bug",
            role="backend",
            priority=1,
            created_at=current_time,
        ),
        Task(
            id="p1-task-2",
            title="Critical bug fix 2",
            description="Fix critical bug",
            role="backend",
            priority=1,
            created_at=current_time,
        ),
        # P2 tasks (normal) - created 10 minutes ago (should get boosted)
        Task(
            id="p2-task-1",
            title="Feature implementation",
            description="Implement feature",
            role="backend",
            priority=2,
            created_at=current_time - 600,  # 10 minutes ago
        ),
        Task(
            id="p2-task-2",
            title="Another feature",
            description="Implement another feature",
            role="backend",
            priority=2,
            created_at=current_time - 600,  # 10 minutes ago
        ),
        # P3 tasks (nice-to-have) - created 15 minutes ago (should get boosted more)
        Task(
            id="p3-task-1",
            title="Documentation update",
            description="Update docs",
            role="backend",
            priority=3,
            created_at=current_time - 900,  # 15 minutes ago
        ),
    ]


def test_fair_scheduling_ages_old_tasks(sample_tasks: list[Task]) -> None:
    """Test that older lower-priority tasks get boosted ahead of newer P1 tasks."""
    # Group tasks with fair scheduling enabled
    task_created_at = {task.id: task.created_at for task in sample_tasks}
    batches = group_by_role(sample_tasks, max_per_batch=1, task_created_at=task_created_at)

    # Extract task IDs in order
    task_order = [batch[0].id for batch in batches]

    # P2 and P3 tasks that are old should be boosted ahead of or interleaved with P1 tasks
    # The exact order depends on the boost calculation, but old tasks should not be last
    p2_indices = [i for i, tid in enumerate(task_order) if tid.startswith("p2")]
    p3_indices = [i for i, tid in enumerate(task_order) if tid.startswith("p3")]
    p1_indices = [i for i, tid in enumerate(task_order) if tid.startswith("p1")]

    # At least some P2/P3 tasks should appear before all P1 tasks are exhausted
    # This ensures fair scheduling is working
    assert min(p2_indices + p3_indices) < max(p1_indices), "Older P2/P3 tasks should be boosted ahead of some P1 tasks"


def test_fair_scheduling_without_timestamps(sample_tasks: list[Task]) -> None:
    """Test that fair scheduling gracefully handles missing timestamps."""
    # Group tasks without timestamp data (should fall back to normal priority ordering)
    batches = group_by_role(sample_tasks, max_per_batch=1, task_created_at=None)

    # Extract task IDs in order
    task_order = [batch[0].id for batch in batches]

    # Without timestamps, tasks should be ordered by priority (P1 first, then P2, then P3)
    # All P1 tasks should come before P2, and all P2 before P3
    p1_indices = [i for i, tid in enumerate(task_order) if tid.startswith("p1")]
    p2_indices = [i for i, tid in enumerate(task_order) if tid.startswith("p2")]
    p3_indices = [i for i, tid in enumerate(task_order) if tid.startswith("p3")]

    assert max(p1_indices) < min(p2_indices), "P1 tasks should come before P2 without aging"
    assert max(p2_indices) < min(p3_indices), "P2 tasks should come before P3 without aging"


def test_fair_scheduling_mixed_roles() -> None:
    """Test fair scheduling works correctly with multiple roles."""
    current_time = time.time()
    tasks = [
        # Backend P1 - new
        Task(
            id="backend-p1-new",
            title="Backend critical",
            description="Critical backend task",
            role="backend",
            priority=1,
            created_at=current_time,
        ),
        # Backend P3 - old (should be boosted)
        Task(
            id="backend-p3-old",
            title="Backend nice-to-have",
            description="Backend documentation",
            role="backend",
            priority=3,
            created_at=current_time - 900,  # 15 minutes ago
        ),
        # QA P1 - new
        Task(
            id="qa-p1-new",
            title="QA critical",
            description="Critical QA task",
            role="qa",
            priority=1,
            created_at=current_time,
        ),
        # QA P2 - old (should be boosted)
        Task(
            id="qa-p2-old",
            title="QA normal",
            description="Normal QA task",
            role="qa",
            priority=2,
            created_at=current_time - 600,  # 10 minutes ago
        ),
    ]

    task_created_at = {task.id: task.created_at for task in tasks}
    batches = group_by_role(tasks, max_per_batch=1, task_created_at=task_created_at)

    # Should have batches from both roles interleaved
    roles_in_order = [batch[0].role for batch in batches]

    # Both roles should be represented
    assert "backend" in roles_in_order
    assert "qa" in roles_in_order

    # Round-robin should interleave roles
    # Check that we don't have all backend tasks before all QA tasks
    backend_indices = [i for i, role in enumerate(roles_in_order) if role == "backend"]
    qa_indices = [i for i, role in enumerate(roles_in_order) if role == "qa"]

    # Roles should be interleaved, not all of one role first
    assert min(qa_indices) < max(backend_indices), "Roles should be interleaved"


def test_priority_age_boost_is_capped_after_many_blocks() -> None:
    """A task that has waited 10 threshold blocks gains only the cap (default: 2) (#4675)."""
    current_time = time.time()
    # P4 task waiting 10 blocks (3000s, threshold 300s)
    # Raw boost would be 10, but cap is 2 -> effective priority = 4 - 2 = 2.
    old_p4 = Task(
        id="old-p4",
        title="Old P4 task",
        description="Low priority backlog item",
        role="backend",
        priority=4,
        created_at=current_time - 3000,
    )
    # Fresh P2 task (effective priority = 2, priority = 2)
    fresh_p2 = Task(
        id="fresh-p2",
        title="Fresh P2 task",
        description="Normal priority task",
        role="backend",
        priority=2,
        created_at=current_time,
    )
    # Fresh P3 task (effective priority = 3)
    fresh_p3 = Task(
        id="fresh-p3",
        title="Fresh P3 task",
        description="Minor task",
        role="backend",
        priority=3,
        created_at=current_time,
    )

    task_created_at = {
        old_p4.id: old_p4.created_at,
        fresh_p2.id: fresh_p2.created_at,
        fresh_p3.id: fresh_p3.created_at,
    }
    batches = group_by_role(
        [old_p4, fresh_p2, fresh_p3],
        max_per_batch=1,
        task_created_at=task_created_at,
    )
    ordered_ids = [b[0].id for b in batches]

    # With cap=2:
    # fresh-p2 (effective 2, priority 2) < old-p4 (effective 2, priority 4) < fresh-p3 (effective 3)
    # If uncapped, old-p4 would have effective priority -6 and come first.
    assert ordered_ids == ["fresh-p2", "old-p4", "fresh-p3"]


def test_fresh_p1_outranks_capped_boost_p3() -> None:
    """A fresh P1 task strictly outranks a P3 task that has reached maximum age boost (#4675)."""
    current_time = time.time()
    fresh_p1 = Task(
        id="fresh-p1",
        title="Critical urgent bug",
        description="P1 urgent",
        role="backend",
        priority=1,
        created_at=current_time,
    )
    # P3 task waiting 10 blocks (3000s, threshold 300s) -> capped at boost 2 -> effective priority 1
    old_p3 = Task(
        id="old-p3-parked",
        title="Parked P3 item",
        description="P3 backlog",
        role="backend",
        priority=3,
        created_at=current_time - 3000,
    )

    task_created_at = {
        fresh_p1.id: fresh_p1.created_at,
        old_p3.id: old_p3.created_at,
    }
    batches = group_by_role(
        [old_p3, fresh_p1],
        max_per_batch=1,
        task_created_at=task_created_at,
    )
    ordered_ids = [b[0].id for b in batches]

    # Fresh P1 must come before old P3
    assert ordered_ids == ["fresh-p1", "old-p3-parked"]


def test_custom_tuning_knobs_respected() -> None:
    """group_by_role respects explicit age_threshold_seconds, boost_amount, and max_age_boost overrides."""
    current_time = time.time()
    task_p3 = Task(
        id="task-p3",
        title="P3 task",
        description="P3",
        role="backend",
        priority=3,
        created_at=current_time - 200,
    )
    task_p2 = Task(
        id="task-p2",
        title="P2 task",
        description="P2",
        role="backend",
        priority=2,
        created_at=current_time,
    )

    task_created_at = {task_p3.id: task_p3.created_at, task_p2.id: task_p2.created_at}

    # With threshold=100s, boost=1, max_boost=2: task_p3 has waited 200s -> boost 2 -> effective priority 1
    # effective priority 1 beats task_p2 effective priority 2
    batches_boosted = group_by_role(
        [task_p2, task_p3],
        max_per_batch=1,
        task_created_at=task_created_at,
        age_threshold_seconds=100.0,
        boost_amount=1,
        max_age_boost=2,
    )
    assert [b[0].id for b in batches_boosted] == ["task-p3", "task-p2"]

    # With max_boost=0 (disabled aging): task_p2 priority 2 beats task_p3 priority 3
    batches_no_boost = group_by_role(
        [task_p2, task_p3],
        max_per_batch=1,
        task_created_at=task_created_at,
        age_threshold_seconds=100.0,
        boost_amount=1,
        max_age_boost=0,
    )
    assert [b[0].id for b in batches_no_boost] == ["task-p2", "task-p3"]

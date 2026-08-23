Fixes #4401

### Problem
When a planning/manager task (`role="manager"`) finishes without creating child tasks, marking it `done` results in the run ledger showing `total=1 done=1 failed=0` and exiting 0 with an empty run branch. This makes a failed decomposition indistinguishable from a run that completed all work.

### Changes
1. In `src/bernstein/core/tasks/task_store_core.py`: In `complete()`, when a task with `role == "manager"` completes and no other child tasks exist in `_tasks`, it transitions to `TaskStatus.FAILED` with `_ZERO_YIELD_PLANNING_REASON` (`Planning task produced no child tasks`) and records a release receipt with `release_path="fail_zero_yield_planning"`.
2. This ensures `failed=1, done=0` so that run health checks and exit code logic detect the failure and exit non-zero.
3. Deliberate refusals via `store.refuse()` cleanly remain `TaskStatus.REFUSED` and distinct from failed decompositions.
4. Added `tests/unit/core/tasks/test_zero_yield_planning_task.py` (4 unit tests).

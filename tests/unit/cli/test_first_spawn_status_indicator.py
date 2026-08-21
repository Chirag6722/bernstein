"""Unit tests for transient TTY status spinner during first agent spawn polling (#4257).

Asserts that ``_await_first_spawn_outcome`` with ``show_status=True`` displays a
transient status indicator when polling takes longer than a single poll interval,
and stays quiet when the first poll succeeds immediately.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from bernstein.cli.run_bootstrap import _await_first_spawn_outcome


def _server_get_factory(responses: list[dict[str, Any] | None]) -> Any:
    iterator = iter(responses)

    def _server_get(path: str) -> Any:
        if path.startswith("/health"):
            try:
                return next(iterator)
            except StopIteration:
                return {"agent_count": 1}
        if path.startswith("/tasks?status=failed"):
            return {"tasks": [], "total": 0, "limit": 50, "offset": 0}
        return None

    return _server_get


def test_first_poll_spawned_prints_nothing() -> None:
    """Fast start: first poll returns agent_count > 0, so status spinner is not shown."""
    stub = _server_get_factory([{"agent_count": 1}])
    with (
        patch("bernstein.cli.run_bootstrap.server_get", side_effect=stub),
        patch("bernstein.cli.helpers.console.status") as mock_status,
    ):
        outcome, reason = _await_first_spawn_outcome(
            timeout_s=1.0,
            poll_interval_s=0.01,
            show_status=True,
        )
    assert outcome == "spawned"
    assert reason is None
    assert not mock_status.called


def test_subsequent_poll_spawned_shows_and_clears_status() -> None:
    """Slow start: first poll returns 0 agents, second poll returns 1 -> status shown and cleared."""
    stub = _server_get_factory([{"agent_count": 0}, {"agent_count": 1}])
    mock_cm = MagicMock()
    with (
        patch("bernstein.cli.run_bootstrap.server_get", side_effect=stub),
        patch("bernstein.cli.helpers.console.status", return_value=mock_cm) as mock_status,
    ):
        outcome, reason = _await_first_spawn_outcome(
            timeout_s=1.0,
            poll_interval_s=0.01,
            show_status=True,
        )
    assert outcome == "spawned"
    assert reason is None
    mock_status.assert_called_once_with("[dim]Waiting for first agent to spawn...[/dim]")
    assert mock_cm.__enter__.called
    assert mock_cm.__exit__.called


def test_show_status_false_does_not_call_status() -> None:
    """Non-interactive / quiet mode: show_status=False never triggers status spinner."""
    stub = _server_get_factory([{"agent_count": 0}, {"agent_count": 1}])
    with (
        patch("bernstein.cli.run_bootstrap.server_get", side_effect=stub),
        patch("bernstein.cli.helpers.console.status") as mock_status,
    ):
        outcome, reason = _await_first_spawn_outcome(
            timeout_s=1.0,
            poll_interval_s=0.01,
            show_status=False,
        )
    assert outcome == "spawned"
    assert reason is None
    assert not mock_status.called

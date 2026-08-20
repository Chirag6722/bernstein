"""Unit tests for opt-in harness-local agent and skill discovery (#3975)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from bernstein.agents.discovery import AgentDiscovery


def test_discovery_off_by_default_touches_nothing_outside_repo(tmp_path: Path) -> None:
    """Issue #3975: Harness-local discovery is OFF by default and returns [] when enabled=False without touching Path.home."""
    discovery = AgentDiscovery(registry_path=tmp_path / "registry.json")
    with patch("pathlib.Path.home", side_effect=RuntimeError("Path.home called when disabled")):
        entries = discovery.discover_harness_local(enabled=False)
    assert entries == []


def test_discovery_on_lists_harness_resources(tmp_path: Path) -> None:
    """Issue #3975: Explicit opt-in discovers harness-local agents and records entry."""
    claude_agents = tmp_path / ".claude" / "agents"
    claude_agents.mkdir(parents=True)
    (claude_agents / "reviewer.md").write_text(
        "---\nname: Code Reviewer\ndescription: Reviews code\n---\nPrompt",
        encoding="utf-8",
    )

    discovery = AgentDiscovery(registry_path=tmp_path / "registry.json", project_dir=tmp_path)

    with patch("pathlib.Path.home", return_value=tmp_path):
        entries = discovery.discover_harness_local(enabled=True)

    assert len(entries) >= 1
    harness_entry = next((e for e in entries if "harness:agents" in e.name), None)
    assert harness_entry is not None
    assert harness_entry.agents == 1
    assert harness_entry.enabled is True


def test_verification_failure_is_listed_as_refused(tmp_path: Path) -> None:
    """Issue #3975: A discovered resource failing lockfile verification is marked as refused (enabled=False, agents=0)."""
    claude_agents = tmp_path / ".claude" / "agents"
    claude_agents.mkdir(parents=True)
    (claude_agents / "reviewer.md").write_text(
        "---\nname: Code Reviewer\ndescription: Reviews code\n---\nPrompt",
        encoding="utf-8",
    )

    # Write mismatched lockfile
    lock_file = claude_agents / "agents.lock"
    lock_file.write_text(json.dumps({"content_digest": "invalid_digest_0000"}), encoding="utf-8")

    discovery = AgentDiscovery(registry_path=tmp_path / "registry.json", project_dir=tmp_path)

    with patch("pathlib.Path.home", return_value=tmp_path):
        entries = discovery.discover_harness_local(enabled=True)

    harness_entry = next((e for e in entries if "harness:agents" in e.name), None)
    assert harness_entry is not None
    assert harness_entry.enabled is False  # Refused due to digest mismatch
    assert harness_entry.agents == 0  # Directory walk was skipped on refusal

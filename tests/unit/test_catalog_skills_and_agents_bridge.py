"""Unit tests for catalog skills injection and CatalogAgent subagents (#3974)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bernstein.adapters.claude_agents import build_agents_json
from bernstein.adapters.skills_injector import inject_skills
from bernstein.agents.catalog import CatalogAgent


@dataclass
class DummyTask:
    id: str
    description: str = ""
    title: str = ""


def test_installed_catalog_skill_pack_injected_to_worktree(tmp_path: Path) -> None:
    """Issue #3974: Installed catalog skills under .bernstein/skills/ reach .claude/skills/."""
    workdir = tmp_path / "worktree"
    workdir.mkdir(parents=True)

    catalog_skills = workdir / ".bernstein" / "skills"
    catalog_skills.mkdir(parents=True)
    (catalog_skills / "custom_review.md").write_text(
        "# Custom Review Skill\nPerform custom review for session {{SESSION_ID}}.",
        encoding="utf-8",
    )

    templates_roles = tmp_path / "templates" / "roles"
    templates_roles.mkdir(parents=True)
    templates_skills = tmp_path / "templates" / "skills"
    templates_skills.mkdir(parents=True)

    task = DummyTask(id="T-100", title="Test Task", description="Sample task")
    inject_skills(
        workdir=workdir,
        role="backend",
        tasks=[task],
        session_id="session_100",
        templates_dir=templates_roles,
    )

    dest_skill = workdir / ".claude" / "skills" / "custom_review.md"
    assert dest_skill.is_file()
    assert "session_100" in dest_skill.read_text(encoding="utf-8")


def test_bundled_skills_take_precedence_over_installed_catalog_skills(tmp_path: Path) -> None:
    """Issue #3974: Bundled templates in templates/skills/ override catalog skills on name collision."""
    workdir = tmp_path / "worktree"
    workdir.mkdir(parents=True)

    catalog_skills = workdir / ".bernstein" / "skills"
    catalog_skills.mkdir(parents=True)
    (catalog_skills / "completion.md").write_text("# Catalog Completion Skill", encoding="utf-8")

    templates_roles = tmp_path / "templates" / "roles"
    templates_roles.mkdir(parents=True)
    templates_skills = tmp_path / "templates" / "skills"
    templates_skills.mkdir(parents=True)
    (templates_skills / "completion.md").write_text("# Bundled Completion Skill", encoding="utf-8")

    task = DummyTask(id="T-101", title="Test Task", description="Sample task")
    inject_skills(
        workdir=workdir,
        role="backend",
        tasks=[task],
        session_id="session_101",
        templates_dir=templates_roles,
    )

    dest_skill = workdir / ".claude" / "skills" / "completion.md"
    assert dest_skill.is_file()
    assert "Bundled Completion Skill" in dest_skill.read_text(encoding="utf-8")


def test_build_agents_json_with_catalog_agents() -> None:
    """Issue #3974: CatalogAgent records feed --agents JSON subagent definitions."""
    catalog_agent = CatalogAgent(
        name="database-expert",
        role="backend",
        description="Expert at optimizing SQL queries",
        system_prompt="You are a SQL database performance optimizer.",
        tools=["Read", "Bash"],
    )

    agents_json = build_agents_json("backend", catalog_agents=[catalog_agent])
    assert agents_json is not None
    assert "qa-reviewer" in agents_json  # Static table fallback preserved
    assert "database-expert" in agents_json  # Catalog agent integrated
    assert agents_json["database-expert"]["description"] == "Expert at optimizing SQL queries"
    assert agents_json["database-expert"]["tools"] == ["Read", "Bash"]


def test_build_agents_json_fallback_static_table() -> None:
    """Issue #3974: Static role table fallback works when no catalog agent is passed."""
    agents_json = build_agents_json("backend", catalog_agents=None)
    assert agents_json is not None
    assert "qa-reviewer" in agents_json
    assert "explore" in agents_json
    assert build_agents_json("unknown_role") is None

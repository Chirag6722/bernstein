"""Build per-task Claude Code subagent definitions for the --agents flag.

Claude Code's ``--agents`` flag accepts a JSON object where keys are subagent
names and values define their behaviour (description, prompt, tools, model).
When a Bernstein-spawned Claude Code agent invokes the Agent tool internally,
these definitions control what subagents are available and how they behave.

This gives Bernstein a second level of orchestration depth: the top-level
agent gets role-scoped subagents for free via Claude Code's built-in
parallelism, without Bernstein needing to manage those subprocesses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bernstein.agents.catalog import CatalogAgent

# ---------------------------------------------------------------------------
# Subagent definitions per role
# ---------------------------------------------------------------------------
# Each role maps to a dict of subagent definitions.  Keys are subagent names,
# values follow Claude Code's AgentJsonSchema:
#   - description (str): when to invoke this subagent
#   - prompt (str): system instructions
#   - tools (list[str]): allowed tool names
#   - model (str, optional): model override
#
# Roles not listed here get no custom subagents (Claude Code defaults apply).
# ---------------------------------------------------------------------------

_SUBAGENTS: dict[str, dict[str, dict[str, Any]]] = {
    "backend": {
        "qa-reviewer": {
            "description": (
                "QA reviewer for validating code changes. Use after making "
                "edits to verify correctness, check for regressions, and "
                "ensure tests pass."
            ),
            "prompt": (
                "You are a QA reviewer. Verify that code changes are correct, "
                "tests pass, and no regressions were introduced. Run tests "
                "with the project's test runner. Report issues clearly with "
                "file paths and line numbers."
            ),
            "tools": ["Bash", "Read", "Grep", "Glob"],
        },
        "explore": {
            "description": (
                "Codebase explorer for understanding architecture and finding "
                "relevant code. Use before making changes to gather context."
            ),
            "prompt": (
                "You are a codebase explorer. Search for relevant files, "
                "understand module structure, and trace dependencies. Report "
                "findings concisely with file paths and key function signatures."
            ),
            "tools": ["Read", "Grep", "Glob"],
        },
    },
    "qa": {
        "explore": {
            "description": (
                "Codebase explorer for finding code to review. Use to locate "
                "files, trace call paths, and understand module structure."
            ),
            "prompt": (
                "You are a codebase explorer assisting a QA reviewer. Search "
                "for relevant files, understand module structure, and trace "
                "dependencies. Report findings with file paths."
            ),
            "tools": ["Read", "Grep", "Glob"],
        },
    },
    "security": {
        "explore": {
            "description": (
                "Codebase explorer for security auditing. Use to find "
                "security-sensitive code paths, credential handling, and "
                "input validation logic."
            ),
            "prompt": (
                "You are a security-focused codebase explorer. Search for "
                "authentication, authorization, input validation, credential "
                "storage, and other security-sensitive code. Report findings "
                "with file paths and risk assessments."
            ),
            "tools": ["Read", "Grep", "Glob", "Bash"],
        },
    },
    "docs": {
        "explore": {
            "description": (
                "Codebase explorer for documentation. Use to find code "
                "structure, public APIs, and existing documentation."
            ),
            "prompt": (
                "You are a codebase explorer assisting a documentation writer. "
                "Search for public APIs, module structure, docstrings, and "
                "existing documentation. Report findings with file paths and "
                "function signatures."
            ),
            "tools": ["Read", "Grep", "Glob"],
        },
    },
}


def build_agents_json(
    role: str,
    catalog_agents: list[CatalogAgent] | None = None,
) -> dict[str, Any] | None:
    """Build --agents JSON for the given role.

    Generates subagent definitions that Claude Code's Agent tool uses when
    the spawned agent delegates subtasks. Merges catalog-matched agents
    with the static per-role subagent table.

    Args:
        role: Agent role (e.g. "backend", "qa", "security", "docs").
        catalog_agents: Optional list of loaded :class:`CatalogAgent` instances.

    Returns:
        Dict suitable for ``json.dumps()`` and passing to ``--agents``,
        or ``None`` if the role has no custom subagent definitions.
    """
    base_agents = _SUBAGENTS.get(role, {})
    result: dict[str, dict[str, Any]] = {name: {**defn} for name, defn in base_agents.items()}

    if catalog_agents:
        for agent in catalog_agents:
            if agent.role == role or role in getattr(agent, "tags", []) or role == "all":
                tools = getattr(agent, "tools", None)
                if not tools:
                    tools = ["Read", "Grep", "Glob", "Bash"]
                sub_def: dict[str, Any] = {
                    "description": agent.description or f"Subagent for {agent.name}",
                    "prompt": getattr(agent, "system_prompt", getattr(agent, "prompt_body", "")),
                    "tools": list(tools),
                }
                model = getattr(agent, "model", None)
                if model:
                    sub_def["model"] = model
                result[agent.name] = sub_def

    if not result:
        return None
    return result

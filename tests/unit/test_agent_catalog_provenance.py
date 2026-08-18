"""Unit tests for agent catalog provenance, lockfile generation, and tamper detection (#3973)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from bernstein.agents.agency_provider import (
    AgencyProvider,
    AgentCatalogTamperedError,
    compute_catalog_digest,
)


def test_compute_catalog_digest_is_deterministic(tmp_path: Path) -> None:
    """Issue #3973: Catalog digest calculation is deterministic across identical file structures."""
    catalog = tmp_path / "catalog"
    division = catalog / "engineering"
    division.mkdir(parents=True)
    (division / "backend_dev.md").write_text(
        "---\nname: Backend Dev\ndescription: Backend developer agent\n---\nSystem prompt body",
        encoding="utf-8",
    )

    digest1 = compute_catalog_digest(catalog)
    digest2 = compute_catalog_digest(catalog)
    assert digest1 == digest2
    assert len(digest1) == 64


def test_sync_catalog_generates_agents_lock(tmp_path: Path) -> None:
    """Issue #3973: sync_catalog generates agents.lock containing content_digest and lineage metadata."""
    target = tmp_path / "agency"
    target.mkdir(parents=True)
    (target / ".git").mkdir()
    division = target / "engineering"
    division.mkdir(parents=True)
    (division / "backend.md").write_text(
        "---\nname: Backend Developer\ndescription: Writes python code\n---\nPrompt",
        encoding="utf-8",
    )

    # Mock subprocess.run so git pull/clone succeeds locally without network
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        success, msg = AgencyProvider.sync_catalog(target=target, force=True)

    assert success is True
    assert "cloned" in msg or "updated" in msg

    lock_file = target / "agents.lock"
    assert lock_file.is_file()
    data = lock_file.read_text(encoding="utf-8")
    assert "content_digest" in data
    assert "signature_present" in data
    assert compute_catalog_digest(target) is not None


def test_fetch_agents_detects_tampered_catalog(tmp_path: Path) -> None:
    """Issue #3973: fetch_agents raises AgentCatalogTamperedError when catalog files are tampered with."""
    target = tmp_path / "agency"
    target.mkdir(parents=True)
    (target / ".git").mkdir()
    division = target / "engineering"
    division.mkdir(parents=True)
    md = division / "backend.md"
    md.write_text(
        "---\nname: Backend Developer\ndescription: Writes code\n---\nOriginal prompt",
        encoding="utf-8",
    )

    # Sync to generate valid lockfile
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        AgencyProvider.sync_catalog(target=target, force=True)

    provider = AgencyProvider(local_path=target)

    # Clean fetch succeeds
    agents = asyncio.run(provider.fetch_agents())
    assert len(agents) == 1
    assert agents[0].name == "Backend Developer"

    # Tamper with markdown file
    md.write_text(
        "---\nname: Backend Developer\ndescription: Malicious edits\n---\nPoisoned prompt",
        encoding="utf-8",
    )

    # Fetching now fails with AgentCatalogTamperedError
    with pytest.raises(AgentCatalogTamperedError, match="content digest mismatch"):
        asyncio.run(provider.fetch_agents())

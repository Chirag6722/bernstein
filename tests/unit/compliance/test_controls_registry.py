"""
Tests for the central compliance control registry (Issue #5455, piece 1).

The suite control declaration and its enforcement in ``bench`` are the
second piece and carry their own tests.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from bernstein.cli.commands.compliance_cmd import compliance_group
from bernstein.compliance.controls import (
    get_default_registry,
)


class TestControlRegistry:
    def test_registry_contains_at_least_30_controls(self) -> None:
        registry = get_default_registry()
        controls = registry.list_controls()
        assert len(controls) >= 30

    def test_controls_cover_all_mandated_frameworks(self) -> None:
        registry = get_default_registry()
        controls = registry.list_controls()
        frameworks_present = set()
        for c in controls:
            assert c.control_id.startswith("CTL-")
            assert len(c.title) > 0
            assert len(c.description) > 0
            assert len(c.evidence_kinds) > 0
            for fw in c.references:
                frameworks_present.add(fw)

        expected_frameworks = {
            "eu_ai_act",
            "owasp_asi",
            "owasp_skills",
            "nist_ai_rmf",
            "iso_42001",
            "finos_aigf",
        }
        for fw in expected_frameworks:
            assert fw in frameworks_present, f"Framework {fw} missing from registry"

    def test_control_lookup(self) -> None:
        registry = get_default_registry()
        c = registry.get("CTL-GOV-01")
        assert c is not None
        assert c.control_id == "CTL-GOV-01"
        assert "eu_ai_act" in c.references
        assert "audit_chain" in c.evidence_kinds or "policy" in c.evidence_kinds or len(c.evidence_kinds) > 0

    def test_filter_by_framework(self) -> None:
        registry = get_default_registry()
        eu_controls = registry.list_controls(framework="eu_ai_act")
        assert len(eu_controls) > 0
        for c in eu_controls:
            assert "eu_ai_act" in c.references

    def test_validate_control_ids(self) -> None:
        registry = get_default_registry()
        assert registry.validate_control_ids(["CTL-GOV-01", "CTL-ROB-01"]) == []
        invalid = registry.validate_control_ids(["CTL-GOV-01", "INVALID-99", "NONEXISTENT"])
        assert invalid == ["INVALID-99", "NONEXISTENT"]

    def test_markdown_table_generation(self) -> None:
        registry = get_default_registry()
        md = registry.to_markdown_table()
        assert "| Control ID | Title | Frameworks | Evidence Kinds |" in md
        assert "CTL-GOV-01" in md


class TestComplianceControlsCLI:
    def test_compliance_controls_text(self) -> None:
        """Through the real root ``cli``, not the group object, so a break in
        ``cli.add_command(compliance_group, "compliance")`` is caught here."""
        from bernstein.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["compliance", "controls"])
        assert result.exit_code == 0
        assert "CTL-GOV-01" in result.output
        assert "Control ID" in result.output or "Title" in result.output

    def test_compliance_controls_json(self) -> None:
        runner = CliRunner()
        result = runner.invoke(compliance_group, ["controls", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 30
        assert any(c["control_id"] == "CTL-GOV-01" for c in data)

    def test_compliance_controls_framework_filter(self) -> None:
        runner = CliRunner()
        result = runner.invoke(compliance_group, ["controls", "--framework", "eu_ai_act", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) > 0
        for c in data:
            assert "eu_ai_act" in c["references"]


class TestRegistryIsDocumented:
    def test_the_docs_table_is_generated_from_the_registry(self) -> None:
        """``docs/compliance/regulator-mapped-packs.md`` carries the registry table verbatim.

        There is no generator script: this test *is* the drift check, and its
        failure message says how to regenerate.
        """
        doc = (Path(__file__).resolve().parents[3] / "docs" / "compliance" / "regulator-mapped-packs.md").read_text(
            encoding="utf-8"
        )
        start = doc.index("-->", doc.index("<!-- controls-table:start")) + len("-->")
        end = doc.index("<!-- controls-table:end -->")
        in_doc = doc[start:end].strip()

        expected = get_default_registry().to_markdown_table().strip()

        assert in_doc == expected, (
            "regulator-mapped-packs.md controls table has drifted from ControlRegistry. Regenerate with: "
            "get_default_registry().to_markdown_table()"
        )

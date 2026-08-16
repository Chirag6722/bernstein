"""Tests for the docs requirements pin gate (#3995).

Every case builds its own ``.in``/``.txt`` pair in a tmp dir. None of them
read the real ``docs/`` files: the drift that motivated this gate is fixed
by #3979, so a test asserting against the real tree would pass from that
moment on and never fail again regardless of whether the check still works.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_docs_requirements_pins import (
    check,
    find_violations,
    parse_in_file,
    parse_pins,
)

# A compiled line carries its hashes on indented continuations. Included
# verbatim in the fixtures because "indented lines are not pins" is a real
# parsing rule, not an incidental formatting detail.
_HASH_TAIL = " \\\n    --hash=sha256:" + "0" * 64


def write_pair(tmp_path: Path, in_text: str, txt_text: str) -> tuple[Path, Path]:
    in_path = tmp_path / "requirements.in"
    txt_path = tmp_path / "requirements.txt"
    in_path.write_text(in_text, encoding="utf-8", newline="")
    txt_path.write_text(txt_text, encoding="utf-8", newline="")
    return in_path, txt_path


class TestTheGateCatchesTheDriftItWasBuiltFor:
    def test_a_pin_above_its_cap_is_a_violation_naming_the_package(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # This is #3995 in miniature: a cap with a reason, and a compiled
        # file that resolved the exact release the cap excludes.
        in_path, txt_path = write_pair(
            tmp_path,
            "# Cap below 1.2.3: that release adds a third-party fork dependency.\nmkdocs-redirects>=1.2,<1.2.3\n",
            f"mkdocs-redirects==1.2.3{_HASH_TAIL}\n",
        )
        assert check(in_path, txt_path) == 1
        out = capsys.readouterr().out
        # The package name is the whole point - "files differ" costs a bisect.
        assert "mkdocs-redirects" in out
        assert "1.2.3" in out
        # And the way out has to be in the failure, not in someone's memory.
        assert "pip-compile" in out

    def test_a_pin_inside_its_bounds_passes(self, tmp_path: Path) -> None:
        in_path, txt_path = write_pair(
            tmp_path,
            "mkdocs-redirects>=1.2,<1.2.3\n",
            f"mkdocs-redirects==1.2.2{_HASH_TAIL}\n",
        )
        assert check(in_path, txt_path) == 0

    def test_the_exact_boundary_version_is_excluded(self, tmp_path: Path) -> None:
        # `<1.2.3` must reject 1.2.3 itself. An off-by-one here would have
        # let the original drift through while still looking like a gate.
        in_path, txt_path = write_pair(tmp_path, "pkg<1.2.3\n", f"pkg==1.2.3{_HASH_TAIL}\n")
        assert check(in_path, txt_path) == 1

    def test_a_directly_declared_requirement_missing_from_the_pins_is_a_violation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A dropped direct dependency is drift too: the docs build stops
        # installing something the .in file says it needs.
        in_path, txt_path = write_pair(
            tmp_path,
            "mkdocs>=1.6.1,<2\nmkdocs-minify-plugin>=0.8,<1\n",
            f"mkdocs==1.6.1{_HASH_TAIL}\n",
        )
        assert check(in_path, txt_path) == 1
        assert "mkdocs-minify-plugin" in capsys.readouterr().out


class TestParsingTheCompiledFormat:
    def test_hash_continuation_lines_are_not_mistaken_for_pins(self) -> None:
        pins = parse_pins(f"babel==2.18.0{_HASH_TAIL}\n    --hash=sha256:" + "1" * 64 + "\n    # via mkdocs-material\n")
        assert pins == {"babel": "2.18.0"}

    def test_extras_are_stripped_when_matching(self, tmp_path: Path) -> None:
        # The committed file is compiled with --strip-extras, so the .in
        # declares `mkdocs-material[imaging]` and the .txt pins the bare name.
        # Matching on the raw string would report a false violation forever.
        in_path, txt_path = write_pair(
            tmp_path,
            "mkdocs-material[imaging]>=9.7.6,<10\n",
            f"mkdocs-material==9.7.6{_HASH_TAIL}\n",
        )
        assert check(in_path, txt_path) == 0

    def test_names_are_compared_canonically(self, tmp_path: Path) -> None:
        # PEP 503: Foo_Bar and foo-bar are the same project.
        in_path, txt_path = write_pair(tmp_path, "Mkdocs_Redirects<1.2.3\n", f"mkdocs-redirects==1.2.2{_HASH_TAIL}\n")
        assert check(in_path, txt_path) == 0

    def test_comments_blank_lines_and_option_lines_are_skipped(self) -> None:
        requirements = parse_in_file(
            "# a comment\n"
            "\n"
            "-r other.in\n"
            "--index-url https://example.invalid/simple\n"
            "mkdocs>=1.6.1,<2  # trailing comment\n"
        )
        assert [r.name for r in requirements] == ["mkdocs"]

    def test_a_version_the_resolver_could_not_produce_is_reported_not_crashed(self, tmp_path: Path) -> None:
        in_path, txt_path = write_pair(tmp_path, "pkg<2\n", "pkg==not-a-version\n")
        assert check(in_path, txt_path) == 1


class TestTheGateRefusesRatherThanPassingOnBadInput:
    def test_an_empty_compiled_file_is_an_error_not_a_pass(self, tmp_path: Path) -> None:
        # The failure that matters most: if the .txt cannot be parsed, every
        # requirement looks "missing" and a naive check reports success on an
        # empty violation list. Refuse instead - this gate exists precisely
        # because a check that reports OK without checking is worse than none.
        in_path, txt_path = write_pair(tmp_path, "mkdocs>=1.6.1,<2\n", "# nothing here\n")
        assert check(in_path, txt_path) == 2

    def test_a_missing_file_is_an_error(self, tmp_path: Path) -> None:
        assert check(tmp_path / "absent.in", tmp_path / "absent.txt") == 2

    def test_an_unparseable_requirement_is_an_error(self, tmp_path: Path) -> None:
        in_path, txt_path = write_pair(tmp_path, "not a requirement!!\n", "pkg==1.0\n")
        assert check(in_path, txt_path) == 2


class TestMarkers:
    def test_a_marker_guarded_requirement_absent_from_the_pins_is_not_a_violation(self) -> None:
        # A Python-version guard can legitimately exclude a requirement from
        # the resolution. Absence is only a finding when it applies always.
        requirements = parse_in_file('tomli>=2; python_version < "3.11"\n')
        assert find_violations(requirements, {"mkdocs": "1.6.1"}) == []

    def test_a_marker_guarded_requirement_that_IS_pinned_is_still_bounds_checked(self) -> None:
        # Present means it was resolved, so the cap applies to it as normal.
        requirements = parse_in_file('tomli>=2,<3; python_version < "3.11"\n')
        violations = find_violations(requirements, {"tomli": "3.1.0"})
        assert [v.name for v in violations] == ["tomli"]

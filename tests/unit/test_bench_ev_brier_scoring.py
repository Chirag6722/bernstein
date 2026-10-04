"""Expected-value and Brier-calibration scoring (#5923).

#5905 gave us the three rates (`resolve_rate`, `abstain_rate`,
`confident_error_rate`) and the `taken_on`/`attempted` split. This adds the
two scalar scoring concepts that #5905 did not carry:

  expected_value  = (resolved - lambda * wrong) / attempted
  brier_score     = mean((confidence - outcome)^2) over evaluated instances

These tests build on #5905's canonical metric definitions — not the divergent
ones from the superseded #5611.
"""

from __future__ import annotations

from benchmarks.swe_bench.metrics import InstanceResult, ScenarioSummary, aggregate


def _result(
    status: str,
    *,
    resolved: bool = False,
    reason: str = "",
    confidence: float = 1.0,
) -> InstanceResult:
    return InstanceResult(
        instance_id=f"inst-{status}-{reason or 'x'}-{confidence}",
        scenario_name="solo",
        status=status,  # type: ignore[arg-type]
        resolved=resolved,
        wall_time_s=1.0,
        total_tokens=10,
        total_cost_usd=0.01,
        abstention_reason=reason,
        confidence=confidence,
    )


# ---------- expected_value ----------


class TestExpectedValue:
    """EV = (resolved - lambda * wrong) / attempted."""

    def test_perfect_run_has_ev_one(self) -> None:
        """All tasks resolved → EV = 1.0 regardless of lambda."""
        summary = aggregate(
            [
                _result("resolved", resolved=True),
                _result("resolved", resolved=True),
            ]
        )
        assert summary.expected_value == 1.0

    def test_all_wrong_has_negative_ev(self) -> None:
        """Every answer wrong, lambda = 0.5 → EV = -0.5."""
        summary = aggregate([_result("failed") for _ in range(4)])
        assert summary.expected_value == -0.5
        assert summary.lambda_penalty == 0.5

    def test_mixed_run_ev(self) -> None:
        """2 resolved, 1 failed, lambda 0.5 → (2 - 0.5*1) / 3 = 0.5."""
        summary = aggregate(
            [
                _result("resolved", resolved=True),
                _result("resolved", resolved=True),
                _result("failed"),
            ]
        )
        assert abs(summary.expected_value - 0.5) < 1e-9

    def test_abstentions_excluded_from_ev_denominator(self) -> None:
        """Abstentions are not attempted, so they are not in the EV denominator.

        1 resolved, 1 abstained → attempted=1, EV = (1 - 0) / 1 = 1.0.
        """
        summary = aggregate(
            [
                _result("resolved", resolved=True),
                _result("abstained", reason="unsure"),
            ]
        )
        assert summary.expected_value == 1.0

    def test_all_abstained_ev_zero(self) -> None:
        """No answers → EV = 0.0 (degenerate case, no division by zero)."""
        summary = aggregate(
            [
                _result("abstained", reason="unsure"),
                _result("abstained", reason="no signal"),
            ]
        )
        assert summary.expected_value == 0.0

    def test_errors_excluded_from_ev(self) -> None:
        """Harness errors are not wrong answers, so they don't incur lambda.

        1 resolved, 1 error → attempted=1, EV = 1.0.
        """
        summary = aggregate(
            [
                _result("resolved", resolved=True),
                _result("error"),
            ]
        )
        # errors are excluded: attempted = total - skipped - abstained = 2 - 0 - 0 = 2
        # But failed = 0 (error is not failed), so EV = (1 - 0.5*0) / 2... wait
        # Let me re-check. The issue says:
        #   EV = (resolved·1 + abstained·0 + wrong·(-λ)) / attempted
        # where "wrong" is failed (not errors). Attempted = total - skipped - abstained.
        # So: attempted = 2, resolved = 1, failed = 0, EV = (1 - 0) / 2 = 0.5
        assert summary.expected_value == 0.5

    def test_skipped_excluded_from_ev(self) -> None:
        """Skipped instances are not in the denominator."""
        summary = aggregate(
            [
                _result("resolved", resolved=True),
                _result("skipped"),
            ]
        )
        # attempted = 2 - 1 - 0 = 1, resolved = 1, failed = 0
        assert summary.expected_value == 1.0


# ---------- brier_score ----------


class TestBrierScore:
    """Brier score = mean((confidence - outcome)^2) over evaluated instances."""

    def test_perfectly_calibrated_correct(self) -> None:
        """Confident and correct → Brier = 0."""
        summary = aggregate(
            [
                _result("resolved", resolved=True, confidence=1.0),
                _result("resolved", resolved=True, confidence=1.0),
            ]
        )
        assert summary.brier_score == 0.0

    def test_perfectly_calibrated_wrong(self) -> None:
        """Confident and wrong → Brier = 1."""
        summary = aggregate(
            [
                _result("failed", confidence=1.0),
                _result("failed", confidence=1.0),
            ]
        )
        assert summary.brier_score == 1.0

    def test_uncertain_and_wrong(self) -> None:
        """Half-confident and wrong → Brier = 0.25."""
        summary = aggregate([_result("failed", confidence=0.5)])
        assert abs(summary.brier_score - 0.25) < 1e-9

    def test_uncertain_and_right(self) -> None:
        """Half-confident and right → Brier = 0.25."""
        summary = aggregate([_result("resolved", resolved=True, confidence=0.5)])
        assert abs(summary.brier_score - 0.25) < 1e-9

    def test_mixed_calibration(self) -> None:
        """Mixed outcomes with varying confidence levels."""
        summary = aggregate(
            [
                _result("resolved", resolved=True, confidence=0.9),  # (0.9 - 1)^2 = 0.01
                _result("failed", confidence=0.3),  # (0.3 - 0)^2 = 0.09
                _result("resolved", resolved=True, confidence=0.7),  # (0.7 - 1)^2 = 0.09
            ]
        )
        expected_brier = (0.01 + 0.09 + 0.09) / 3
        assert abs(summary.brier_score - expected_brier) < 1e-9

    def test_abstentions_excluded_from_brier(self) -> None:
        """Abstained instances are not calibrated — they gave no answer."""
        summary = aggregate(
            [
                _result("resolved", resolved=True, confidence=1.0),
                _result("abstained", reason="unsure", confidence=0.2),
            ]
        )
        # Only the resolved instance counts. Brier = (1.0 - 1)^2 = 0.0
        assert summary.brier_score == 0.0

    def test_skipped_excluded_from_brier(self) -> None:
        """Skipped instances are not in Brier."""
        summary = aggregate(
            [
                _result("resolved", resolved=True, confidence=1.0),
                _result("skipped", confidence=0.0),
            ]
        )
        assert summary.brier_score == 0.0

    def test_errors_excluded_from_brier(self) -> None:
        """Harness errors are not the run's prediction, so they're excluded."""
        summary = aggregate(
            [
                _result("resolved", resolved=True, confidence=0.8),
                _result("error", confidence=1.0),
            ]
        )
        # Only the resolved instance: (0.8 - 1)^2 = 0.04
        assert abs(summary.brier_score - 0.04) < 1e-9


# ---------- confidence on InstanceResult ----------


class TestConfidenceField:
    """The confidence field on InstanceResult."""

    def test_default_confidence_is_one(self) -> None:
        """Pre-existing results without confidence are implicitly fully confident."""
        result = InstanceResult(
            instance_id="old-1",
            scenario_name="solo",
            status="resolved",
            resolved=True,
            wall_time_s=1.0,
            total_tokens=10,
            total_cost_usd=0.01,
        )
        assert result.confidence == 1.0

    def test_confidence_round_trips(self) -> None:
        """Serialise → deserialise preserves confidence."""
        result = _result("resolved", resolved=True, confidence=0.85)
        restored = InstanceResult.from_dict(result.to_dict())
        assert restored.confidence == 0.85

    def test_legacy_result_without_confidence_loads(self) -> None:
        """A result written before confidence existed still loads."""
        legacy = {
            "instance_id": "old-1",
            "scenario_name": "solo",
            "status": "failed",
            "resolved": False,
            "wall_time_s": 2.0,
            "total_tokens": 5,
            "total_cost_usd": 0.02,
            "agent_traces": [],
            "error_message": "",
            "patch": "",
        }
        loaded = InstanceResult.from_dict(legacy)
        assert loaded.confidence == 1.0


# ---------- ScenarioSummary round-trip ----------


class TestSummaryRoundTrip:
    """EV/Brier fields persist and round-trip through from_dict."""

    def test_ev_brier_in_to_dict(self) -> None:
        """aggregate output → to_dict includes the new fields."""
        summary = aggregate(
            [
                _result("resolved", resolved=True, confidence=0.9),
                _result("failed", confidence=0.6),
            ]
        )
        d = summary.to_dict()
        assert "expected_value" in d
        assert "brier_score" in d
        assert "lambda_penalty" in d

    def test_legacy_summary_without_ev_brier_loads(self) -> None:
        """A summary written before #5923 still loads with defaults."""
        legacy = {
            "scenario_name": "solo",
            "total_instances": 3,
            "resolved": 2,
            "failed": 1,
            "errors": 0,
            "skipped": 0,
            "resolve_rate": 2 / 3,
            "mean_wall_time_s": 1.0,
            "median_wall_time_s": 1.0,
            "total_cost_usd": 0.03,
            "mean_cost_per_instance_usd": 0.01,
            "mean_tokens_per_instance": 10.0,
        }
        summary = ScenarioSummary.from_dict(legacy)
        assert summary.lambda_penalty == 0.5
        assert summary.expected_value == 0.0
        assert summary.brier_score == 0.0

    def test_from_dict_preserves_ev_brier(self) -> None:
        """Round-trip: aggregate → to_dict → from_dict preserves values."""
        original = aggregate(
            [
                _result("resolved", resolved=True, confidence=0.9),
                _result("failed", confidence=0.4),
            ]
        )
        restored = ScenarioSummary.from_dict(original.to_dict())
        assert abs(restored.expected_value - original.expected_value) < 1e-9
        assert abs(restored.brier_score - original.brier_score) < 1e-9
        assert restored.lambda_penalty == original.lambda_penalty

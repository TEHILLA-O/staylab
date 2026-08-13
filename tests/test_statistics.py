"""Two-proportion z-test, uplift, confidence interval, decision logic."""

from __future__ import annotations

import math

import pytest

from analytics.statistical_tests import (
    decide,
    sample_ratio_mismatch,
    two_proportion_ztest,
)


def _example() -> tuple[int, int, int, int]:
    # The numbers from the product brief, used as a known-good fixture.
    return 4_903, 49_871, 5_427, 50_129


def test_conversion_rates_and_uplift() -> None:
    test = two_proportion_ztest(*_example())
    assert test.control_rate == pytest.approx(4_903 / 49_871)
    assert test.treatment_rate == pytest.approx(5_427 / 50_129)
    assert test.absolute_uplift == pytest.approx(
        test.treatment_rate - test.control_rate
    )
    assert test.relative_uplift == pytest.approx(
        test.absolute_uplift / test.control_rate
    )
    assert 0.009 < test.absolute_uplift < 0.011
    assert 0.09 < test.relative_uplift < 0.12


def test_ztest_is_significant_for_the_brief_example() -> None:
    test = two_proportion_ztest(*_example())
    assert test.p_value < 0.05
    assert test.statistically_significant
    assert test.z_score > 0
    lo, hi = test.confidence_interval
    assert lo > 0
    assert hi > lo
    assert lo < test.absolute_uplift < hi


def test_identical_arms_are_not_significant() -> None:
    test = two_proportion_ztest(500, 5_000, 500, 5_000)
    assert test.absolute_uplift == 0
    assert test.relative_uplift == 0
    assert test.p_value > 0.9
    assert not test.statistically_significant
    lo, hi = test.confidence_interval
    assert lo < 0 < hi


def test_rejects_invalid_counts() -> None:
    with pytest.raises(ValueError):
        two_proportion_ztest(10, 0, 5, 10)
    with pytest.raises(ValueError):
        two_proportion_ztest(12, 10, 5, 10)


def test_confidence_interval_widens_with_smaller_n() -> None:
    large = two_proportion_ztest(4_903, 49_871, 5_427, 50_129)
    small = two_proportion_ztest(49, 499, 54, 501)
    large_width = large.confidence_interval[1] - large.confidence_interval[0]
    small_width = small.confidence_interval[1] - small.confidence_interval[0]
    assert small_width > large_width


def test_standard_error_matches_unpooled_formula() -> None:
    test = two_proportion_ztest(*_example())
    p_a, n_a = test.control_rate, test.control_visitors
    p_b, n_b = test.treatment_rate, test.treatment_visitors
    expected = math.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b)
    assert test.standard_error == pytest.approx(expected)


def test_decide_ships_when_effect_is_real_and_material() -> None:
    test = two_proportion_ztest(*_example())
    decision = decide(test, practical_significance_threshold=0.01)
    assert decision.verdict == "significant"
    assert decision.decision == "ship"
    assert decision.guardrails_ok


def test_decide_does_not_ship_on_p_value_alone() -> None:
    # Huge n, 1% relative lift: significant, not worth shipping.
    test = two_proportion_ztest(200_000, 2_000_000, 202_000, 2_000_000)
    assert test.statistically_significant
    decision = decide(test, practical_significance_threshold=0.05)
    assert decision.decision == "iterate"
    assert decision.verdict == "significant"


def test_decide_keep_running_when_ci_includes_zero() -> None:
    test = two_proportion_ztest(98, 1_000, 105, 1_000)
    assert not test.statistically_significant
    decision = decide(test)
    assert decision.verdict == "inconclusive"
    assert decision.decision == "keep_running"


def test_decide_do_not_ship_when_treatment_loses() -> None:
    test = two_proportion_ztest(5_400, 50_000, 4_900, 50_000)
    decision = decide(test)
    assert decision.verdict == "negative"
    assert decision.decision == "do_not_ship"


def test_decide_vetoes_on_sample_ratio_mismatch() -> None:
    test = two_proportion_ztest(*_example())
    srm = sample_ratio_mismatch(40_000, 60_000, alpha=0.001)
    assert srm.mismatch_detected
    decision = decide(test, srm=srm)
    assert decision.decision == "do_not_ship"
    assert decision.verdict == "inconclusive"


def test_decide_iterates_when_a_guardrail_breaches() -> None:
    test = two_proportion_ztest(*_example())
    decision = decide(test, guardrail_breaches=["Cancellation rate moved +12.0%"])
    assert decision.decision == "iterate"
    assert not decision.guardrails_ok


def test_balanced_split_is_not_a_mismatch() -> None:
    srm = sample_ratio_mismatch(49_871, 50_129)
    assert not srm.mismatch_detected
    assert srm.observed_ratio == pytest.approx(50_129 / (49_871 + 50_129))

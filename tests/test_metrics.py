"""Metric arithmetic that the dashboard must never invent itself."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from analytics.power_analysis import minimum_detectable_effect, required_sample_size


def _rates(control_bookings: int, control_visitors: int,
           treatment_bookings: int, treatment_visitors: int) -> dict[str, float]:
    control = control_bookings / control_visitors
    treatment = treatment_bookings / treatment_visitors
    absolute = treatment - control
    relative = absolute / control
    return {
        "control": control,
        "treatment": treatment,
        "absolute": absolute,
        "relative": relative,
    }


def test_absolute_and_relative_uplift_match_the_brief() -> None:
    result = _rates(4_903, 49_871, 5_427, 50_129)
    assert result["control"] == pytest.approx(0.0983, abs=5e-5)
    assert result["treatment"] == pytest.approx(0.1083, abs=5e-5)
    assert result["absolute"] == pytest.approx(0.01, abs=5e-4)
    assert result["relative"] == pytest.approx(0.102, abs=5e-3)


def test_revenue_per_visitor_includes_non_converters() -> None:
    visitors = pd.Series([0.0, 0.0, 0.0, 240.0, 0.0])
    assert visitors.mean() == pytest.approx(48.0)
    booked_only = visitors[visitors > 0].mean()
    assert booked_only == pytest.approx(240.0)
    assert visitors.mean() < booked_only


def test_required_sample_size_grows_as_mde_shrinks() -> None:
    loose = required_sample_size(0.10, mde_relative=0.10)
    tight = required_sample_size(0.10, mde_relative=0.05)
    assert tight.required_per_variant > loose.required_per_variant
    assert tight.mde_absolute == pytest.approx(0.005)


def test_mde_shrinks_with_more_traffic() -> None:
    small = minimum_detectable_effect(0.10, 5_000)
    large = minimum_detectable_effect(0.10, 50_000)
    assert large["mde_absolute"] < small["mde_absolute"]
    assert large["mde_relative"] < small["mde_relative"]


def test_power_rejects_impossible_baseline() -> None:
    with pytest.raises(ValueError):
        required_sample_size(0.0, 0.05)
    with pytest.raises(ValueError):
        required_sample_size(1.2, 0.05)


def test_relative_uplift_undefined_when_control_is_zero() -> None:
    from analytics.statistical_tests import two_proportion_ztest

    test = two_proportion_ztest(0, 1_000, 12, 1_000)
    assert math.isnan(test.relative_uplift)

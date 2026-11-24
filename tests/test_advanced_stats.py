import numpy as np
import pandas as pd
from analytics.advanced_stats import (
    bootstrap_lift,
    cuped,
    msprt_pvalues,
    multiple_testing,
    srm_report,
)


def _users(n=20000, effect=0.01, seed=0):
    rng = np.random.default_rng(seed)
    treat = rng.integers(0, 2, n)
    x = rng.normal(size=n)
    p = np.clip(0.15 + 0.08 * x + effect * treat, 0.001, 0.999)
    y = (rng.random(n) < p).astype(int)
    return pd.DataFrame({
        "variant": np.where(treat == 1, "B", "A"),
        "treat": treat,
        "converted": y,
        "revenue": y * rng.gamma(2.0, 60.0, n),
        "x": x,
        "day": rng.integers(0, 14, n),
        "device": rng.choice(["desktop", "mobile"], n),
        "traffic_source": rng.choice(["direct", "search"], n),
        "room_type": rng.choice(["Entire home/apt", "Private room"], n),
        "neighbourhood": rng.choice(list("ABCDE"), n),
    })


def test_cuped_reduces_variance_with_a_predictive_covariate():
    u = _users()
    x = (u["x"] - u["x"].mean()).to_numpy()[:, None]
    out = cuped(u["converted"].to_numpy(float), x, u["treat"].to_numpy())
    assert out["variance_reduction"] > 0.03
    assert out["adjusted"]["se"] < out["unadjusted"]["se"]
    assert abs(out["adjusted"]["estimate"] - out["unadjusted"]["estimate"]) < 0.005


def test_cuped_with_noise_covariate_changes_little():
    u = _users()
    noise = np.random.default_rng(9).normal(size=(len(u), 1))
    out = cuped(u["converted"].to_numpy(float), noise - noise.mean(), u["treat"].to_numpy())
    assert out["variance_reduction"] < 0.01


def test_msprt_pvalues_are_monotone_and_bounded():
    n = np.arange(1, 15) * 1000.0
    p = msprt_pvalues(n * 0.10, n, n * 0.11, n)
    assert np.all(np.diff(p) <= 0)
    assert np.all((p >= 0) & (p <= 1))


def test_msprt_is_more_conservative_than_a_single_z_test():
    from analytics.statistical_tests import two_proportion_ztest

    p_av = msprt_pvalues(np.array([1000.0]), np.array([10000.0]), np.array([1100.0]), np.array([10000.0]))
    p_z = two_proportion_ztest(1000, 10000, 1100, 10000).p_value
    assert p_av[0] > p_z


def test_multiple_testing_adjustment_never_adds_findings():
    out = multiple_testing(_users(effect=0.0))
    assert out["significant_holm"] <= out["significant_bh"] <= out["significant_unadjusted"]


def test_srm_passes_on_random_assignment():
    assert srm_report(_users())["overall"]["mismatch_detected"] is False


def test_bootstrap_interval_contains_point_estimate():
    b = bootstrap_lift(_users(), n_boot=300)["converted"]
    assert b["absolute_ci"][0] <= b["absolute_diff"] <= b["absolute_ci"][1]

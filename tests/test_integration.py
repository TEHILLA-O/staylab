"""Optional SQL integration tests. Skipped when PostgreSQL is not loaded."""

from __future__ import annotations

import pytest

from analytics.db import get_engine, ping, read_query, scalar

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine():
    eng = get_engine()
    if not ping(eng):
        pytest.skip("PostgreSQL is not reachable")
    n = scalar("SELECT COUNT(*) FROM experiment_users", engine=eng)
    if not n:
        pytest.skip("experiment data is not loaded")
    return eng


def test_conversion_query_returns_both_variants(engine) -> None:
    df = read_query("conversion", {"experiment_id": 1}, engine)
    assert set(df["variant"]) == {"A", "B"}
    assert (df["visitors"] > 0).all()
    assert (df["conversion_rate"].between(0, 1)).all()


def test_sample_ratio_has_no_contaminated_users(engine) -> None:
    row = read_query("sample_ratio_mismatch", {"experiment_id": 1}, engine).iloc[0]
    assert int(row["users_in_both_variants"]) == 0
    assert int(row["control_users"]) + int(row["treatment_users"]) == int(row["total_users"])


def test_daily_metrics_cover_the_run(engine) -> None:
    df = read_query("daily_metrics", {"experiment_id": 1}, engine)
    assert len(df) >= 10
    assert df["control_cumulative"].notna().all()
    assert df["treatment_cumulative"].notna().all()


def test_segmentation_flags_small_neighbourhoods(engine) -> None:
    df = read_query(
        "segmentation",
        {"experiment_id": 1, "segment_type": "device", "row_limit": 10},
        engine,
    )
    assert {"mobile", "desktop", "tablet"} <= set(df["segment_value"])

"""Randomisation: 50/50 in expectation, one variant per user, never forced."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.generate_experiment import ExperimentGenerator
from analytics.statistical_tests import sample_ratio_mismatch


def test_assignment_is_approximately_balanced(tiny_listings: pd.DataFrame) -> None:
    gen = ExperimentGenerator(tiny_listings, seed=20260619)
    users = gen.assign_users(10_000)
    counts = users["variant"].value_counts()
    assert set(counts.index) == {"A", "B"}
    # A genuine 50/50 draw of 10k will not land on exactly 5000/5000.
    assert counts["A"] != counts["B"]
    srm = sample_ratio_mismatch(int(counts["A"]), int(counts["B"]))
    assert not srm.mismatch_detected
    assert 0.48 < srm.observed_ratio < 0.52


def test_assignment_is_reproducible(tiny_listings: pd.DataFrame) -> None:
    a = ExperimentGenerator(tiny_listings, seed=99).assign_users(500)
    b = ExperimentGenerator(tiny_listings, seed=99).assign_users(500)
    pd.testing.assert_frame_equal(a, b)


def test_different_seeds_produce_different_splits(tiny_listings: pd.DataFrame) -> None:
    a = ExperimentGenerator(tiny_listings, seed=1).assign_users(800)
    b = ExperimentGenerator(tiny_listings, seed=2).assign_users(800)
    assert not np.array_equal(a["variant"].to_numpy(), b["variant"].to_numpy())


def test_user_never_appears_in_both_variants(
    tiny_listings: pd.DataFrame, small_experiment_config
) -> None:
    data = ExperimentGenerator(
        tiny_listings, config=small_experiment_config, seed=20260619
    ).run()
    variants_per_user = data["sessions"].groupby("user_id")["variant"].nunique()
    assert (variants_per_user == 1).all()
    assigned = data["users"].set_index("user_id")["variant"]
    session_variant = data["sessions"].drop_duplicates("user_id").set_index("user_id")["variant"]
    aligned = assigned.reindex(session_variant.index)
    assert (aligned == session_variant).all()


def test_session_count_is_near_the_configured_target(
    tiny_listings: pd.DataFrame, small_experiment_config
) -> None:
    data = ExperimentGenerator(
        tiny_listings, config=small_experiment_config, seed=11
    ).run()
    # Poisson fan-out around sessions_per_user, not an exact force.
    assert 500 < len(data["sessions"]) < 1_400

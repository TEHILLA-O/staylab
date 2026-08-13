"""Simulation integrity: funnel order, bookings, listing-driven probabilities."""

from __future__ import annotations

import pandas as pd

from analytics.generate_experiment import ExperimentGenerator, listing_appeal


def test_funnel_is_monotonic(tiny_listings: pd.DataFrame, small_experiment_config) -> None:
    data = ExperimentGenerator(
        tiny_listings, config=small_experiment_config, seed=20260619
    ).run()
    sessions = data["sessions"]
    assert (sessions.loc[sessions["started_checkout"], "clicked_cta"]).all()
    assert (sessions.loc[sessions["converted"], "started_checkout"]).all()


def test_every_session_has_view_and_exit(
    tiny_listings: pd.DataFrame, small_experiment_config
) -> None:
    data = ExperimentGenerator(
        tiny_listings, config=small_experiment_config, seed=3
    ).run()
    events = data["events"]
    types = set(events["event_type"].unique())
    assert {"listing_view", "session_exit"} <= types
    per_session = events.groupby("session_id")["event_type"].apply(set)
    assert per_session.map(lambda s: {"listing_view", "session_exit"} <= s).all()


def test_bookings_match_converted_sessions(
    tiny_listings: pd.DataFrame, small_experiment_config
) -> None:
    data = ExperimentGenerator(
        tiny_listings, config=small_experiment_config, seed=5
    ).run()
    converted_ids = set(data["sessions"].loc[data["sessions"]["converted"], "session_id"])
    booking_ids = set(data["bookings"]["session_id"])
    assert converted_ids == booking_ids
    assert (data["bookings"]["booking_value"] > 0).all()
    assert (data["bookings"]["nights"] >= 1).all()


def test_events_never_precede_session_start(
    tiny_listings: pd.DataFrame, small_experiment_config
) -> None:
    data = ExperimentGenerator(
        tiny_listings, config=small_experiment_config, seed=8
    ).run()
    merged = data["events"].merge(
        data["sessions"][["session_id", "session_started_at"]], on="session_id"
    )
    assert (merged["event_timestamp"] >= merged["session_started_at"]).all()


def test_listing_appeal_rewards_quality(tiny_listings: pd.DataFrame) -> None:
    listings = tiny_listings.copy()
    listings.loc[0, ["review_scores_rating", "has_review_score",
                     "host_is_superhost", "price_vs_neighbourhood"]] = [4.95, True, True, 0.7]
    listings.loc[1, ["review_scores_rating", "has_review_score",
                     "host_is_superhost", "price_vs_neighbourhood"]] = [3.90, True, False, 2.2]
    appeal = listing_appeal(listings)
    assert appeal[0] > appeal[1]


def test_treatment_does_not_hard_code_final_rates(
    tiny_listings: pd.DataFrame, small_experiment_config
) -> None:
    a = ExperimentGenerator(tiny_listings, config=small_experiment_config, seed=1).run()
    b = ExperimentGenerator(tiny_listings, config=small_experiment_config, seed=2).run()
    rate_a = float(a["sessions"]["converted"].mean())
    rate_b = float(b["sessions"]["converted"].mean())
    assert rate_a != rate_b

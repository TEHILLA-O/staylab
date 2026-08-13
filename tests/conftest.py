"""Shared fixtures. Heavy listings / database fixtures stay optional."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analytics.config import ExperimentConfig


@pytest.fixture
def tiny_listings() -> pd.DataFrame:
    """A handful of listings with the columns the simulator actually reads."""
    rng = np.random.default_rng(7)
    n = 40
    neighbourhoods = np.array(["Hackney", "Westminster", "Camden", "Lambeth"])
    room_types = np.array(["Entire home/apt", "Private room", "Hotel room", "Shared room"])
    prices = rng.uniform(40, 280, size=n).round(2)
    return pd.DataFrame({
        "listing_id": np.arange(1000, 1000 + n, dtype=np.int64),
        "neighbourhood": rng.choice(neighbourhoods, size=n),
        "room_type": rng.choice(room_types, size=n, p=[0.55, 0.35, 0.06, 0.04]),
        "price": prices,
        "accommodates": rng.integers(1, 6, size=n),
        "review_scores_rating": rng.choice(
            [np.nan, 4.2, 4.6, 4.8, 4.95], size=n, p=[0.15, 0.15, 0.25, 0.3, 0.15]
        ),
        "has_review_score": True,
        "host_is_superhost": rng.random(n) < 0.28,
        "instant_bookable": rng.random(n) < 0.4,
        "price_vs_neighbourhood": rng.uniform(0.6, 1.6, size=n).round(4),
        "number_of_reviews": rng.integers(0, 180, size=n),
        "number_of_reviews_ltm": rng.integers(0, 40, size=n),
        "reviews_per_month": rng.uniform(0.0, 3.5, size=n).round(2),
        "calendar_availability_rate": rng.uniform(0.15, 0.85, size=n).round(4),
        "calendar_avg_price": prices,
        "calendar_min_nights": rng.choice([1, 2, 3, 5], size=n),
    }).assign(has_review_score=lambda d: d["review_scores_rating"].notna())


@pytest.fixture
def small_experiment_config() -> ExperimentConfig:
    return ExperimentConfig(n_sessions=800, n_days=14, seed=20260619)

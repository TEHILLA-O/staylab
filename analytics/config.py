"""Central configuration for the StayLab analytics pipeline.

Everything that a reviewer might want to tweak (snapshot date, sample size,
treatment effect, random seed) lives here or in the environment, never inline
in the simulation code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DATABASE_DIR = PROJECT_ROOT / "database"
QUERY_DIR = DATABASE_DIR / "queries"
SCHEMA_FILE = DATABASE_DIR / "schema.sql"


def _env(key: str, default: str) -> str:
    value = os.getenv(key)
    return default if value is None or value == "" else value


def database_url() -> str:
    """Resolve the SQLAlchemy URL, preferring an explicit DATABASE_URL."""
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    user = _env("POSTGRES_USER", "staylab")
    password = _env("POSTGRES_PASSWORD", "staylab")
    host = _env("POSTGRES_HOST", "localhost")
    port = _env("POSTGRES_PORT", "5434")
    name = _env("POSTGRES_DB", "staylab")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


# --------------------------------------------------------------------------
# Source data
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceConfig:
    city: str = _env("INSIDE_AIRBNB_CITY", "london")
    snapshot: str = _env("INSIDE_AIRBNB_SNAPSHOT", "2026-06-19")
    base_url: str = _env(
        "INSIDE_AIRBNB_BASE_URL",
        "https://data.insideairbnb.com/united-kingdom/england/london",
    )

    @property
    def raw_dir(self) -> Path:
        return RAW_DIR / self.city

    @property
    def files(self) -> dict[str, str]:
        return {
            "listings.csv.gz": f"{self.base_url}/{self.snapshot}/data/listings.csv.gz",
            "calendar.csv.gz": f"{self.base_url}/{self.snapshot}/data/calendar.csv.gz",
            "neighbourhoods.csv": (
                f"{self.base_url}/{self.snapshot}/visualisations/neighbourhoods.csv"
            ),
        }


# --------------------------------------------------------------------------
# Experiment definition
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExperimentConfig:
    """Definition of EXP-024, the simplified booking experience test."""

    experiment_key: str = "EXP-024"
    name: str = "Simplified booking experience"
    hypothesis: str = (
        "Showing the all-in total price alongside the nightly rate, with a more "
        "prominent Reserve call to action, increases booking conversion."
    )
    randomisation_unit: str = "user"
    primary_metric: str = "booking_conversion_rate"

    seed: int = int(_env("EXPERIMENT_SEED", "20260619"))
    n_sessions: int = int(_env("EXPERIMENT_SESSIONS", "100000"))
    n_days: int = int(_env("EXPERIMENT_DAYS", "14"))
    start_date: date = field(
        default_factory=lambda: date.fromisoformat(
            _env("EXPERIMENT_START_DATE", "2026-06-19")
        )
    )

    # Allocation probability for [control, treatment]. Never post-hoc forced.
    allocation: tuple[float, float] = (0.5, 0.5)

    # Average sessions per user; drives the user -> session fan-out.
    sessions_per_user: float = 1.18

    # ---- Funnel baselines (probabilities for an "average" listing/session) --
    # Calibrated so the user-level control rate lands near 9.8%, in the range
    # a high-intent booking surface plausibly sees. The realised rate comes out
    # slightly above the raw product of these three because session-level
    # heterogeneity is convex through the logistic link.
    base_cta_click: float = 0.332
    base_checkout_given_cta: float = 0.394
    base_booking_given_checkout: float = 0.508

    # ---- Treatment effects, expressed as additive shifts on the logit scale.
    # The redesign mostly helps at the CTA and checkout steps: the price is
    # unambiguous before the user commits.
    treatment_logit_cta: float = 0.052
    treatment_logit_checkout: float = 0.087
    treatment_logit_booking: float = 0.043

    # Novelty effect: the shift is inflated on the first days then decays to 1.0.
    novelty_multiplier: float = 1.55
    novelty_halflife_days: float = 3.0

    # Guardrails
    base_cancellation_rate: float = 0.072
    treatment_logit_cancellation: float = -0.070

    # Treatment surfaces the total cost, which slightly shortens booked stays.
    treatment_nights_multiplier: float = 0.978

    significance_level: float = 0.05
    mde_relative: float = 0.05  # 5% relative lift the test was powered to detect


SOURCE = SourceConfig()
EXPERIMENT = ExperimentConfig()

DEVICES: tuple[str, ...] = ("mobile", "desktop", "tablet")
DEVICE_WEIGHTS: tuple[float, ...] = (0.63, 0.31, 0.06)

TRAFFIC_SOURCES: tuple[str, ...] = (
    "organic_search",
    "paid_search",
    "direct",
    "email",
    "paid_social",
    "referral",
)
TRAFFIC_WEIGHTS: tuple[float, ...] = (0.34, 0.19, 0.21, 0.09, 0.11, 0.06)

EVENT_TYPES: tuple[str, ...] = (
    "listing_view",
    "cta_click",
    "checkout_started",
    "booking_completed",
    "session_exit",
)

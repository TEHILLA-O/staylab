"""Load processed listings and the generated experiment into PostgreSQL."""

from __future__ import annotations

import argparse

import pandas as pd
from sqlalchemy import Engine, text

from analytics.config import EXPERIMENT, PROCESSED_DIR, ExperimentConfig
from analytics.db import (
    apply_schema,
    copy_dataframe,
    get_engine,
    ping,
    refresh_materialized_views,
    truncate,
)
from analytics.generate_experiment import generate
from analytics.logging_config import get_logger

log = get_logger(__name__)

LISTING_COLUMNS = [
    "listing_id", "host_id", "neighbourhood", "latitude", "longitude",
    "property_type", "room_type", "accommodates", "bedrooms", "beds", "price",
    "price_per_person", "neighbourhood_median_price", "price_vs_neighbourhood",
    "minimum_nights", "maximum_nights", "availability_365", "number_of_reviews",
    "number_of_reviews_ltm", "reviews_per_month", "review_scores_rating",
    "has_review_score", "review_scores_value", "review_scores_location",
    "instant_bookable", "host_is_superhost", "estimated_occupancy_l365d",
    "last_review", "calendar_availability_rate", "calendar_avg_price",
    "calendar_min_nights",
]

# Columns typed as SMALLINT/INTEGER in the schema. Pandas widens these to
# float whenever a NULL is present, and COPY will not accept "1.0" for an int.
LISTING_INT_COLUMNS = [
    "host_id", "accommodates", "bedrooms", "beds", "minimum_nights",
    "maximum_nights", "availability_365", "number_of_reviews",
    "number_of_reviews_ltm", "estimated_occupancy_l365d",
]

NEIGHBOURHOOD_COLUMNS = [
    "neighbourhood", "listings", "median_price", "avg_price", "avg_review_score",
    "superhost_share", "instant_bookable_share", "entire_home_share",
]


def upsert_experiment(engine: Engine, cfg: ExperimentConfig) -> int:
    end_date = pd.Timestamp(cfg.start_date) + pd.Timedelta(days=cfg.n_days - 1)
    sql = text("""
        INSERT INTO experiments (
            experiment_key, name, surface, hypothesis, primary_metric,
            randomisation_unit, status, significance_level, started_at, ended_at
        ) VALUES (
            :key, :name, :surface, :hypothesis, :primary_metric,
            :unit, :status, :alpha, :started_at, :ended_at
        )
        ON CONFLICT (experiment_key) DO UPDATE SET
            name = EXCLUDED.name,
            hypothesis = EXCLUDED.hypothesis,
            primary_metric = EXCLUDED.primary_metric,
            significance_level = EXCLUDED.significance_level,
            started_at = EXCLUDED.started_at,
            ended_at = EXCLUDED.ended_at
        RETURNING experiment_id
    """)
    with engine.begin() as conn:
        return conn.execute(sql, {
            "key": cfg.experiment_key,
            "name": cfg.name,
            "surface": "Booking Flow",
            "hypothesis": cfg.hypothesis,
            "primary_metric": cfg.primary_metric,
            "unit": cfg.randomisation_unit,
            "status": "running",
            "alpha": cfg.significance_level,
            "started_at": cfg.start_date,
            "ended_at": end_date.date(),
        }).scalar_one()


def load_listings(engine: Engine) -> int:
    path = PROCESSED_DIR / "listings.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python -m analytics.etl_listings` first."
        )
    listings = pd.read_parquet(path)
    listings = listings.reindex(columns=LISTING_COLUMNS)
    listings["last_review"] = pd.to_datetime(listings["last_review"]).dt.date
    for col in LISTING_INT_COLUMNS:
        listings[col] = listings[col].round().astype("Int64")
    truncate(["listings"], engine=engine)
    return copy_dataframe(listings, "listings", LISTING_COLUMNS, engine=engine)


def load_neighbourhoods(engine: Engine) -> int:
    path = PROCESSED_DIR / "neighbourhoods.parquet"
    if not path.exists():
        return 0
    frame = pd.read_parquet(path).reindex(columns=NEIGHBOURHOOD_COLUMNS)
    truncate(["neighbourhoods"], engine=engine)
    return copy_dataframe(frame, "neighbourhoods", NEIGHBOURHOOD_COLUMNS, engine=engine)


def load_experiment(engine: Engine, data: dict[str, pd.DataFrame],
                    experiment_id: int) -> dict[str, int]:
    truncate(
        ["experiment_events", "bookings", "experiment_sessions", "experiment_users"],
        engine=engine,
    )

    users = data["users"].copy()
    users["experiment_id"] = experiment_id
    counts = {
        "experiment_users": copy_dataframe(
            users, "experiment_users",
            ["user_id", "experiment_id", "variant", "assigned_at"], engine=engine,
        )
    }

    sessions = data["sessions"].copy()
    sessions["experiment_id"] = experiment_id
    counts["experiment_sessions"] = copy_dataframe(
        sessions, "experiment_sessions",
        ["session_id", "user_id", "experiment_id", "listing_id", "variant",
         "session_started_at", "device", "traffic_source", "is_returning_user"],
        engine=engine,
    )

    counts["experiment_events"] = copy_dataframe(
        data["events"], "experiment_events",
        ["session_id", "event_type", "event_timestamp", "sequence_no"], engine=engine,
    )

    counts["bookings"] = copy_dataframe(
        data["bookings"], "bookings",
        ["booking_id", "session_id", "listing_id", "booking_value", "nights",
         "guests", "checkin_date", "created_at", "is_cancelled", "cancelled_at"],
        engine=engine,
    )

    with engine.begin() as conn:
        conn.execute(text("ANALYZE experiment_sessions, experiment_events, bookings"))
    refresh_materialized_views(engine)
    return counts


def run(skip_listings: bool = False, seed: int | None = None,
        cfg: ExperimentConfig | None = None) -> dict[str, int]:
    cfg = cfg or EXPERIMENT
    engine = get_engine()
    if not ping(engine):
        raise ConnectionError(
            "Cannot reach PostgreSQL. Start it with `docker compose up -d db`."
        )

    apply_schema(engine)
    experiment_id = upsert_experiment(engine, cfg)

    counts: dict[str, int] = {}
    if not skip_listings:
        counts["listings"] = load_listings(engine)
        counts["neighbourhoods"] = load_neighbourhoods(engine)

    data = generate(config=cfg, seed=seed)
    counts.update(load_experiment(engine, data, experiment_id))

    log.info("database load complete", extra=counts)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Load StayLab data into PostgreSQL")
    parser.add_argument("--skip-listings", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    run(skip_listings=args.skip_listings, seed=args.seed)


if __name__ == "__main__":
    main()

"""ETL for the Inside Airbnb London snapshot.

Reads the untouched files in ``data/raw/london`` and writes tidy parquet to
``data/processed``. The raw files are never modified.

Outputs
-------
listings.parquet        one row per bookable listing, cleaned and typed
calendar_summary.parquet  per-listing forward availability/price from calendar
neighbourhoods.parquet  borough-level aggregates used by the simulation
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from analytics.config import PROCESSED_DIR, SOURCE
from analytics.logging_config import get_logger

log = get_logger(__name__)

LISTING_COLUMNS = [
    "id",
    "host_id",
    "host_is_superhost",
    "neighbourhood_cleansed",
    "latitude",
    "longitude",
    "property_type",
    "room_type",
    "accommodates",
    "bedrooms",
    "beds",
    "price",
    "minimum_nights",
    "maximum_nights",
    "has_availability",
    "availability_365",
    "number_of_reviews",
    "number_of_reviews_ltm",
    "review_scores_rating",
    "review_scores_value",
    "review_scores_location",
    "instant_bookable",
    "reviews_per_month",
    "estimated_occupancy_l365d",
    "last_review",
]

# Guards against scraper artefacts (£0 rooms, £30k "penthouses") that would
# otherwise dominate revenue metrics.
MIN_PRICE = 15.0
MAX_PRICE = 2000.0


def _to_bool(series: pd.Series) -> pd.Series:
    """Inside Airbnb encodes booleans as 't'/'f'/blank."""
    return series.astype("string").str.lower().eq("t").fillna(False).astype(bool)


def _to_price(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype("string")
        .str.replace(r"[$,]", "", regex=True)
        .str.strip()
        .replace({"": None})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def clean_listings(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.rename(columns={"id": "listing_id", "neighbourhood_cleansed": "neighbourhood"})

    df["price"] = _to_price(df["price"])
    df["host_is_superhost"] = _to_bool(df["host_is_superhost"])
    df["instant_bookable"] = _to_bool(df["instant_bookable"])
    df["has_availability"] = _to_bool(df["has_availability"])

    numeric = [
        "accommodates", "bedrooms", "beds", "minimum_nights", "maximum_nights",
        "availability_365", "number_of_reviews", "number_of_reviews_ltm",
        "review_scores_rating", "review_scores_value", "review_scores_location",
        "reviews_per_month", "estimated_occupancy_l365d", "latitude", "longitude",
    ]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["last_review"] = pd.to_datetime(df["last_review"], errors="coerce")

    before = len(df)
    df = df[df["price"].between(MIN_PRICE, MAX_PRICE, inclusive="both")]
    df = df[df["room_type"].notna()]
    df = df[df["neighbourhood"].notna()]
    df = df[df["accommodates"].fillna(0) > 0]
    # A listing a visitor could realistically be shown: some forward inventory.
    df = df[(df["availability_365"].fillna(0) > 0) | (df["has_availability"])]
    log.info(
        "listings filtered",
        extra={"before": before, "after": len(df), "dropped": before - len(df)},
    )

    df["bedrooms"] = df["bedrooms"].fillna(df["accommodates"].div(2).round()).clip(lower=0)
    df["beds"] = df["beds"].fillna(df["bedrooms"].clip(lower=1))
    df["minimum_nights"] = df["minimum_nights"].fillna(1).clip(1, 90).astype(int)
    df["maximum_nights"] = (
        df["maximum_nights"].fillna(365).clip(df["minimum_nights"], 1125).astype(int)
    )
    df["number_of_reviews"] = df["number_of_reviews"].fillna(0).astype(int)
    df["number_of_reviews_ltm"] = df["number_of_reviews_ltm"].fillna(0).astype(int)
    df["reviews_per_month"] = df["reviews_per_month"].fillna(0.0)
    df["estimated_occupancy_l365d"] = df["estimated_occupancy_l365d"].fillna(0).astype(int)
    df["accommodates"] = df["accommodates"].astype(int)
    df["availability_365"] = df["availability_365"].fillna(0).astype(int)

    # review_scores_rating is genuinely missing for never-reviewed listings.
    # Keep the NULL rather than imputing: the simulation treats "no score yet"
    # as its own state, which is how a real ranking model would see it.
    df["has_review_score"] = df["review_scores_rating"].notna()

    df["price_per_person"] = (df["price"] / df["accommodates"]).round(2)

    borough_price = df.groupby("neighbourhood")["price"].transform("median")
    df["neighbourhood_median_price"] = borough_price.round(2)
    df["price_vs_neighbourhood"] = (df["price"] / borough_price).round(4)

    keep = [
        "listing_id", "host_id", "neighbourhood", "latitude", "longitude",
        "property_type", "room_type", "accommodates", "bedrooms", "beds",
        "price", "price_per_person", "neighbourhood_median_price",
        "price_vs_neighbourhood", "minimum_nights", "maximum_nights",
        "availability_365", "number_of_reviews", "number_of_reviews_ltm",
        "reviews_per_month", "review_scores_rating", "has_review_score",
        "review_scores_value", "review_scores_location", "instant_bookable",
        "host_is_superhost", "estimated_occupancy_l365d", "last_review",
    ]
    return df[keep].reset_index(drop=True)


def summarise_calendar(path: Path, listing_ids: set[int],
                       chunk_size: int = 2_000_000) -> pd.DataFrame:
    """Aggregate the (very large) calendar file into per-listing statistics.

    Read in chunks so the 30M+ row file never has to fit in memory at once.

    The June 2026 snapshot dropped the per-night ``price`` column that older
    Inside Airbnb calendars carried, so nightly rates come from the listings
    file and the calendar contributes forward availability and the minimum-stay
    rule actually in force.
    """
    horizon_days = 180
    acc: dict[int, dict[str, float]] = {}
    rows_read = 0

    reader = pd.read_csv(
        path,
        compression="gzip",
        usecols=["listing_id", "date", "available", "minimum_nights"],
        chunksize=chunk_size,
        low_memory=False,
    )
    horizon_end: pd.Timestamp | None = None

    for chunk in reader:
        rows_read += len(chunk)
        chunk = chunk[chunk["listing_id"].isin(listing_ids)]
        if chunk.empty:
            continue
        chunk["date"] = pd.to_datetime(chunk["date"], errors="coerce")
        if horizon_end is None:
            horizon_end = chunk["date"].min() + pd.Timedelta(days=horizon_days)
        chunk = chunk[chunk["date"] <= horizon_end]
        if chunk.empty:
            continue

        chunk["is_available"] = chunk["available"].astype("string").str.lower().eq("t")
        chunk["min_nights"] = pd.to_numeric(chunk["minimum_nights"], errors="coerce")

        grouped = chunk.groupby("listing_id").agg(
            nights=("date", "size"),
            available_nights=("is_available", "sum"),
            min_nights_sum=("min_nights", "sum"),
            min_nights_count=("min_nights", "count"),
        )
        for listing_id, row in grouped.iterrows():
            bucket = acc.setdefault(
                int(listing_id),
                {"nights": 0.0, "available_nights": 0.0,
                 "min_nights_sum": 0.0, "min_nights_count": 0.0},
            )
            for key in bucket:
                bucket[key] += float(row[key])

    log.info("calendar scanned", extra={"rows": rows_read, "listings": len(acc)})

    if not acc:
        return pd.DataFrame(
            columns=["listing_id", "calendar_nights", "calendar_available_nights",
                     "calendar_availability_rate", "calendar_min_nights"]
        )

    out = pd.DataFrame.from_dict(acc, orient="index").rename_axis("listing_id").reset_index()
    out["calendar_nights"] = out["nights"].astype(int)
    out["calendar_available_nights"] = out["available_nights"].astype(int)
    out["calendar_availability_rate"] = (
        out["available_nights"] / out["nights"].replace(0, np.nan)
    ).round(4)
    out["calendar_min_nights"] = (
        out["min_nights_sum"] / out["min_nights_count"].replace(0, np.nan)
    ).round(1)

    return out[[
        "listing_id", "calendar_nights", "calendar_available_nights",
        "calendar_availability_rate", "calendar_min_nights",
    ]]


def build_neighbourhoods(listings: pd.DataFrame) -> pd.DataFrame:
    agg = (
        listings.groupby("neighbourhood")
        .agg(
            listings=("listing_id", "size"),
            median_price=("price", "median"),
            avg_price=("price", "mean"),
            avg_review_score=("review_scores_rating", "mean"),
            superhost_share=("host_is_superhost", "mean"),
            instant_bookable_share=("instant_bookable", "mean"),
            entire_home_share=("room_type", lambda s: (s == "Entire home/apt").mean()),
        )
        .reset_index()
    )
    for col in ("median_price", "avg_price", "avg_review_score"):
        agg[col] = agg[col].round(2)
    for col in ("superhost_share", "instant_bookable_share", "entire_home_share"):
        agg[col] = agg[col].round(4)
    return agg.sort_values("listings", ascending=False).reset_index(drop=True)


def run(skip_calendar: bool = False) -> dict[str, Path]:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    raw_dir = SOURCE.raw_dir

    listings_path = raw_dir / "listings.csv.gz"
    if not listings_path.exists():
        raise FileNotFoundError(
            f"{listings_path} not found. Run `python -m analytics.download_data` first."
        )

    log.info("reading listings", extra={"path": str(listings_path)})
    raw = pd.read_csv(
        listings_path, compression="gzip", usecols=LISTING_COLUMNS, low_memory=False
    )
    listings = clean_listings(raw)

    calendar_path = raw_dir / "calendar.csv.gz"
    if not skip_calendar and calendar_path.exists():
        cal = summarise_calendar(calendar_path, set(listings["listing_id"].tolist()))
        cal.to_parquet(PROCESSED_DIR / "calendar_summary.parquet", index=False)
        listings = listings.merge(cal, on="listing_id", how="left")
    else:
        log.warning("calendar step skipped")
        for col in ("calendar_availability_rate", "calendar_min_nights"):
            listings[col] = np.nan

    # Kept as a column so downstream code has a single "nightly rate to charge"
    # field even though this snapshot's calendar no longer publishes prices.
    listings["calendar_avg_price"] = listings["price"]
    listings["calendar_min_nights"] = (
        listings["calendar_min_nights"].fillna(listings["minimum_nights"]).clip(1, 30)
    )
    listings["calendar_availability_rate"] = listings["calendar_availability_rate"].fillna(
        (listings["availability_365"] / 365).clip(0, 1)
    )

    neighbourhoods = build_neighbourhoods(listings)

    out_listings = PROCESSED_DIR / "listings.parquet"
    out_neigh = PROCESSED_DIR / "neighbourhoods.parquet"
    listings.to_parquet(out_listings, index=False)
    neighbourhoods.to_parquet(out_neigh, index=False)

    log.info(
        "etl complete",
        extra={
            "listings": len(listings),
            "neighbourhoods": len(neighbourhoods),
            "median_price": float(listings["price"].median()),
        },
    )
    return {"listings": out_listings, "neighbourhoods": out_neigh}


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean the Inside Airbnb London snapshot")
    parser.add_argument("--skip-calendar", action="store_true",
                        help="skip the large calendar aggregation")
    args = parser.parse_args()
    run(skip_calendar=args.skip_calendar)


if __name__ == "__main__":
    main()

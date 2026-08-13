"""SQL library: files exist, are parameterised, and never accept caller SQL."""

from __future__ import annotations

from pathlib import Path

import pytest

from analytics.config import QUERY_DIR
from analytics.db import load_query
from api.services.experiments import SQL_CATALOGUE, get_sql_query


REQUIRED = [
    "experiment_summary",
    "conversion",
    "revenue",
    "segmentation",
    "daily_metrics",
    "sample_ratio_mismatch",
    "funnel",
    "guardrails",
    "marketplace_overview",
]


def test_every_catalogue_query_has_a_file() -> None:
    for name in SQL_CATALOGUE:
        path = QUERY_DIR / f"{name}.sql"
        assert path.exists(), path
        sql = path.read_text(encoding="utf-8")
        assert "SELECT" in sql.upper()


def test_required_portfolio_queries_are_present() -> None:
    for name in REQUIRED:
        assert (QUERY_DIR / f"{name}.sql").exists()


def test_core_queries_use_named_parameters() -> None:
    for name in ("experiment_summary", "conversion", "segmentation",
                 "daily_metrics", "sample_ratio_mismatch"):
        sql = load_query(name)
        assert ":experiment_id" in sql


def test_queries_demonstrate_sql_features() -> None:
    joined = "\n".join(load_query(name) for name in REQUIRED)
    upper = joined.upper()
    assert "JOIN" in upper
    assert "GROUP BY" in upper
    assert "CASE" in upper
    assert "WITH " in upper
    assert "OVER" in upper


def test_unknown_sql_name_is_rejected() -> None:
    with pytest.raises(Exception):
        get_sql_query("drop_everything")


def test_schema_separates_real_and_simulated_tables() -> None:
    schema = Path("database/schema.sql").read_text(encoding="utf-8")
    for table in ("listings", "experiment_sessions", "experiment_events", "bookings"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema
    assert "SIMULATED" in schema

"""Service layer between the HTTP routes and the analytics package.

Routes stay thin: they resolve an identifier, call one of these functions and
hand the result to a Pydantic model.
"""

from __future__ import annotations

from typing import Any

from analytics import experiment_service as core
from analytics.db import get_engine, load_query
from analytics.logging_config import get_logger
from analytics.validation import run as run_validation

log = get_logger(__name__)


class ExperimentNotFound(LookupError):
    pass


# Curated catalogue for the dashboard's SQL tab. Only these named queries can
# ever be surfaced, and they are read-only files on disk — the API never
# accepts SQL from a caller.
SQL_CATALOGUE: dict[str, dict[str, str]] = {
    "experiment_summary": {
        "title": "Experiment summary",
        "description": (
            "Per-variant funnel and revenue metrics, with uplift against control "
            "computed in SQL using a window function rather than a self-join."
        ),
    },
    "conversion": {
        "title": "Primary metric — conversion",
        "description": (
            "Booking conversion at both analysis units. The user-level rate feeds "
            "the significance test because the user is the randomisation unit."
        ),
    },
    "daily_metrics": {
        "title": "Daily & cumulative conversion",
        "description": (
            "Daily and running conversion per variant. The cumulative series is "
            "built with a window frame in the underlying view."
        ),
    },
    "segmentation": {
        "title": "Segment comparison",
        "description": (
            "One parameterised query serving device, traffic source, "
            "neighbourhood and room type, with underpowered segments flagged."
        ),
    },
    "funnel": {
        "title": "Funnel step analysis",
        "description": (
            "Step-by-step conversion showing where in the flow the treatment "
            "actually moved the numbers."
        ),
    },
    "revenue": {
        "title": "Revenue metrics",
        "description": (
            "Gross and net revenue, average booking value and revenue per "
            "visitor, with the standard deviations the Welch test needs."
        ),
    },
    "guardrails": {
        "title": "Guardrail metrics",
        "description": "Cancellation, abandonment and bounce rates by variant.",
    },
    "sample_ratio_mismatch": {
        "title": "Sample ratio mismatch",
        "description": (
            "Allocation health check, plus an assertion that no user was ever "
            "exposed to both variants."
        ),
    },
    "marketplace_overview": {
        "title": "Marketplace context",
        "description": (
            "Aggregates over the real Inside Airbnb London listings the "
            "experiment sampled traffic from."
        ),
    },
}


def resolve_experiment_id(identifier: str | int) -> int:
    """Accept either a numeric id or an experiment key such as EXP-024."""
    engine = get_engine()
    if isinstance(identifier, int) or str(identifier).isdigit():
        return int(identifier)
    for row in core.list_experiments(engine):
        if row["experiment_key"].lower() == str(identifier).lower():
            return int(row["experiment_id"])
    raise ExperimentNotFound(f"No experiment matching {identifier!r}")


def list_experiments() -> list[dict[str, Any]]:
    return core.list_experiments(get_engine())


def get_experiment(experiment_id: int) -> dict[str, Any]:
    try:
        return core.get_experiment(experiment_id, get_engine())
    except core.ExperimentNotFound as exc:
        raise ExperimentNotFound(str(exc)) from exc


def get_summary(experiment_id: int) -> list[dict[str, Any]]:
    return core.get_summary(experiment_id, get_engine())


def get_timeseries(experiment_id: int) -> list[dict[str, Any]]:
    return core.get_timeseries(experiment_id, get_engine())


def get_segments(experiment_id: int, segment_type: str, limit: int) -> dict[str, Any]:
    rows = core.get_segments(experiment_id, segment_type, limit, get_engine())
    return {"segment_type": segment_type, "rows": rows}


def get_funnel(experiment_id: int) -> list[dict[str, Any]]:
    return core.get_funnel(experiment_id, get_engine())


def get_marketplace(experiment_id: int) -> dict[str, Any]:
    return core.get_marketplace(experiment_id, get_engine())


def get_statistics(experiment_id: int) -> dict[str, Any]:
    try:
        return core.analyse(experiment_id, get_engine())["statistics"]
    except core.ExperimentNotFound as exc:
        raise ExperimentNotFound(str(exc)) from exc


def get_analysis(experiment_id: int, include_validation: bool = True) -> dict[str, Any]:
    engine = get_engine()
    try:
        payload = core.analyse(experiment_id, engine)
    except core.ExperimentNotFound as exc:
        raise ExperimentNotFound(str(exc)) from exc

    if include_validation:
        checks, _ = run_validation(experiment_id, engine)
        payload["validation"] = [
            {"name": c.name, "passed": c.passed, "detail": c.detail,
             "severity": c.severity}
            for c in checks
        ]
    return payload


def list_sql_queries() -> list[dict[str, str]]:
    return [
        {"name": name, "title": meta["title"], "description": meta["description"],
         "sql": load_query(name)}
        for name, meta in SQL_CATALOGUE.items()
    ]


def get_sql_query(name: str) -> dict[str, str]:
    if name not in SQL_CATALOGUE:
        raise ExperimentNotFound(f"No SQL query named {name!r}")
    meta = SQL_CATALOGUE[name]
    return {"name": name, "title": meta["title"],
            "description": meta["description"], "sql": load_query(name)}

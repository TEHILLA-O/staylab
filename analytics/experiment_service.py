"""The analysis layer: SQL aggregates in, decision out.

Deliberately framework-free. The CLI readout and the FastAPI endpoints both
call into here, which is what guarantees the dashboard and the terminal can
never disagree.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Engine

from analytics.db import get_engine, read_query, read_sql
from analytics.logging_config import get_logger
from analytics.power_analysis import minimum_detectable_effect, required_sample_size
from analytics.statistical_tests import (
    decide,
    sample_ratio_mismatch,
    two_proportion_ztest,
    welch_ttest_from_summary,
)

log = get_logger(__name__)


class ExperimentNotFound(LookupError):
    pass


# How much a guardrail may move in the wrong direction before it counts as a
# regression. Small movements on large samples are still noise in practice.
GUARDRAIL_TOLERANCE = 0.05  # 5% relative

GUARDRAIL_LABELS = {
    "cancellation_rate": "Cancellation rate",
    "checkout_abandon_rate": "Checkout abandonment",
    "bounce_rate": "Bounce rate",
    "avg_session_seconds": "Avg. session length",
}

# Booking value is what the guest pays. The marketplace only books the fee it
# takes out of that, so the business impact of the experiment is the fee on the
# incremental bookings, not their headline value.
PLATFORM_TAKE_RATE = 0.15


def _clean(value: Any) -> Any:
    """Make numpy/NaN values JSON- and Pydantic-friendly."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if pd.isna(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if pd.isna(value) if np.isscalar(value) else False:
        return None
    return value


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict("records")]


# --------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------


def list_experiments(engine: Engine | None = None) -> list[dict[str, Any]]:
    engine = engine or get_engine()
    df = read_sql(
        """
        SELECT
            e.experiment_id,
            e.experiment_key,
            e.name,
            e.surface,
            e.status,
            e.primary_metric,
            e.randomisation_unit,
            e.significance_level,
            e.started_at,
            e.ended_at,
            e.is_simulated,
            e.data_source,
            COUNT(DISTINCT u.user_id) AS users,
            COUNT(s.session_id)       AS sessions
        FROM experiments e
        LEFT JOIN experiment_users u    ON u.experiment_id = e.experiment_id
        LEFT JOIN experiment_sessions s ON s.experiment_id = e.experiment_id
        GROUP BY e.experiment_id
        ORDER BY e.started_at DESC
        """,
        engine=engine,
    )
    return _records(df)


def get_experiment(experiment_id: int, engine: Engine | None = None) -> dict[str, Any]:
    engine = engine or get_engine()
    df = read_sql(
        """
        SELECT
            e.*,
            (SELECT COUNT(*) FROM experiment_users u
             WHERE u.experiment_id = e.experiment_id)     AS users,
            (SELECT COUNT(*) FROM experiment_sessions s
             WHERE s.experiment_id = e.experiment_id)     AS sessions,
            (SELECT MIN(session_started_at) FROM experiment_sessions s
             WHERE s.experiment_id = e.experiment_id)     AS first_session_at,
            (SELECT MAX(session_started_at) FROM experiment_sessions s
             WHERE s.experiment_id = e.experiment_id)     AS last_session_at
        FROM experiments e
        WHERE e.experiment_id = :eid
        """,
        {"eid": experiment_id}, engine,
    )
    if df.empty:
        raise ExperimentNotFound(f"No experiment with id {experiment_id}")

    row = {k: _clean(v) for k, v in df.iloc[0].items()}
    first, last = df.iloc[0]["first_session_at"], df.iloc[0]["last_session_at"]
    if pd.notna(first) and pd.notna(last):
        row["duration_days"] = int((last.normalize() - first.normalize()).days) + 1
        row["first_session_at"] = first.isoformat()
        row["last_session_at"] = last.isoformat()
    else:
        row["duration_days"] = 0
    return row


# --------------------------------------------------------------------------
# Aggregates
# --------------------------------------------------------------------------


def summary_frame(experiment_id: int, engine: Engine | None = None) -> pd.DataFrame:
    df = read_query("experiment_summary", {"experiment_id": experiment_id}, engine)
    if df.empty:
        raise ExperimentNotFound(f"No results for experiment {experiment_id}")
    return df.set_index("variant")


def get_summary(experiment_id: int, engine: Engine | None = None) -> list[dict[str, Any]]:
    df = read_query("experiment_summary", {"experiment_id": experiment_id}, engine)
    return _records(df)


def get_timeseries(experiment_id: int, engine: Engine | None = None) -> list[dict[str, Any]]:
    df = read_query("daily_metrics", {"experiment_id": experiment_id}, engine)
    return _records(df)


def get_segments(experiment_id: int, segment_type: str = "device",
                 limit: int = 25, engine: Engine | None = None) -> list[dict[str, Any]]:
    allowed = {"device", "traffic_source", "neighbourhood", "room_type"}
    if segment_type not in allowed:
        raise ValueError(f"segment_type must be one of {sorted(allowed)}")
    df = read_query(
        "segmentation",
        {"experiment_id": experiment_id, "segment_type": segment_type,
         "row_limit": int(limit)},
        engine,
    )
    return _records(df)


def get_funnel(experiment_id: int, engine: Engine | None = None) -> list[dict[str, Any]]:
    return _records(read_query("funnel", {"experiment_id": experiment_id}, engine))


def get_marketplace(experiment_id: int, engine: Engine | None = None) -> dict[str, Any]:
    df = read_query("marketplace_overview", {"experiment_id": experiment_id}, engine)
    return {k: _clean(v) for k, v in df.iloc[0].items()} if not df.empty else {}


# --------------------------------------------------------------------------
# Inference
# --------------------------------------------------------------------------


def _guardrails(experiment_id: int, engine: Engine | None) -> list[dict[str, Any]]:
    df = read_query("guardrails", {"experiment_id": experiment_id}, engine)
    out = []
    for row in df.to_dict("records"):
        relative = _clean(row["relative_change"])
        direction = row["direction"]
        breached = (
            direction == "lower_is_better"
            and relative is not None
            and relative > GUARDRAIL_TOLERANCE
        )
        out.append({
            "metric": row["metric"],
            "label": GUARDRAIL_LABELS.get(row["metric"], row["metric"]),
            "direction": direction,
            "control_value": _clean(row["control_value"]),
            "treatment_value": _clean(row["treatment_value"]),
            "absolute_change": _clean(row["absolute_change"]),
            "relative_change": relative,
            "breached": bool(breached),
        })
    return out


def _secondary_metrics(summary: pd.DataFrame,
                       revenue: pd.DataFrame) -> list[dict[str, Any]]:
    specs = [
        ("cta_click_rate", "CTA click rate", "percent", summary),
        ("checkout_start_rate", "Checkout-start rate", "percent", summary),
        ("session_conversion_rate", "Session conversion rate", "percent", summary),
        ("bounce_rate", "Bounce rate", "percent", summary),
        ("revenue_per_visitor", "Revenue per visitor", "currency", revenue),
        ("average_booking_value", "Average booking value", "currency", revenue),
    ]
    out = []
    for key, label, fmt, source in specs:
        if key not in source.columns:
            continue
        control = _clean(source.loc["A", key])
        treatment = _clean(source.loc["B", key])
        if control in (None, 0):
            relative = None
        else:
            relative = (treatment - control) / control
        out.append({
            "metric": key,
            "label": label,
            "format": fmt,
            "control_value": control,
            "treatment_value": treatment,
            "absolute_change": None if control is None else treatment - control,
            "relative_change": relative,
        })
    return out


def analyse(experiment_id: int, engine: Engine | None = None) -> dict[str, Any]:
    """Full readout: metadata, aggregates, inference and recommendation."""
    engine = engine or get_engine()
    experiment = get_experiment(experiment_id, engine)
    alpha = float(experiment.get("significance_level") or 0.05)

    summary = summary_frame(experiment_id, engine)
    if not {"A", "B"}.issubset(summary.index):
        raise ExperimentNotFound("Experiment does not have both variants loaded")

    revenue = read_query("revenue", {"experiment_id": experiment_id},
                         engine).set_index("variant")

    # Primary metric at the randomisation unit.
    primary = two_proportion_ztest(
        control_conversions=int(summary.loc["A", "converted_users"]),
        control_visitors=int(summary.loc["A", "users"]),
        treatment_conversions=int(summary.loc["B", "converted_users"]),
        treatment_visitors=int(summary.loc["B", "users"]),
        alpha=alpha,
    )

    # Secondary proportion tests, computed on sessions.
    secondary_tests: dict[str, dict[str, Any]] = {}
    for key, num, den in (
        ("cta_click_rate", "cta_clicks", "sessions"),
        ("checkout_start_rate", "checkout_starts", "sessions"),
        ("session_conversion_rate", "conversions", "sessions"),
    ):
        secondary_tests[key] = two_proportion_ztest(
            control_conversions=int(summary.loc["A", num]),
            control_visitors=int(summary.loc["A", den]),
            treatment_conversions=int(summary.loc["B", num]),
            treatment_visitors=int(summary.loc["B", den]),
            alpha=alpha,
        ).to_dict()

    # Revenue per visitor: continuous and heavily zero-inflated, so Welch.
    rpv_test = welch_ttest_from_summary(
        control_mean=float(revenue.loc["A", "revenue_per_visitor"]),
        control_sd=float(revenue.loc["A", "revenue_per_visitor_stddev"]),
        control_n=int(revenue.loc["A", "visitors"]),
        treatment_mean=float(revenue.loc["B", "revenue_per_visitor"]),
        treatment_sd=float(revenue.loc["B", "revenue_per_visitor_stddev"]),
        treatment_n=int(revenue.loc["B", "visitors"]),
        alpha=alpha,
    )

    srm_row = read_query("sample_ratio_mismatch",
                         {"experiment_id": experiment_id}, engine).iloc[0]
    srm = sample_ratio_mismatch(int(srm_row["control_users"]),
                                int(srm_row["treatment_users"]))

    guardrails = _guardrails(experiment_id, engine)
    breaches = [
        f"{g['label']} moved {g['relative_change']:+.1%}"
        for g in guardrails if g["breached"]
    ]
    decision = decide(primary, srm=srm, guardrail_breaches=breaches)

    mde = minimum_detectable_effect(primary.control_rate, primary.control_visitors,
                                    alpha=alpha)
    planned = required_sample_size(primary.control_rate, mde_relative=0.05, alpha=alpha)

    # Annualise from the traffic the experiment actually observed rather than
    # from an invented market size, so the projection is traceable to measured
    # numbers and one clearly stated assumption.
    duration_days = max(int(experiment.get("duration_days") or 0), 1)
    total_users = int(summary["users"].sum())
    annual_visitors = int(round(total_users / duration_days * 365))

    rpv_delta = rpv_test.absolute_uplift
    has_delta = rpv_delta == rpv_delta  # False when NaN
    gross_delta = rpv_delta * annual_visitors if has_delta else None
    projected = {
        "annual_visitors": annual_visitors,
        "revenue_per_visitor_delta": rpv_delta if has_delta else None,
        "annualised_gross_booking_delta": gross_delta,
        "platform_take_rate": PLATFORM_TAKE_RATE,
        "annualised_revenue_delta": (
            gross_delta * PLATFORM_TAKE_RATE if gross_delta is not None else None
        ),
        "basis": (
            f"Observed traffic of {total_users:,} randomised visitors over "
            f"{duration_days} days annualises to ~{annual_visitors:,} visitors. "
            f"Applying the measured revenue-per-visitor difference and a "
            f"{PLATFORM_TAKE_RATE:.0%} platform take rate gives the figure above. "
            "It is a projection under flat traffic and a persistent effect, not a "
            "measured outcome, and the novelty effect visible in the first days "
            "means the long-run number is likely lower."
        ),
    }

    return {
        "experiment": experiment,
        "summary": _records(summary.reset_index()),
        "secondary_metrics": _secondary_metrics(summary, revenue),
        "guardrails": guardrails,
        "statistics": {
            "primary": primary.to_dict(),
            "secondary": secondary_tests,
            "revenue_per_visitor": rpv_test.to_dict(),
            "sample_ratio": srm.to_dict(),
            "minimum_detectable_effect": mde,
            "planned_sample_size": planned.to_dict(),
        },
        "decision": {
            "verdict": decision.verdict,
            "decision": decision.decision,
            "headline": decision.headline,
            "rationale": decision.rationale,
            "guardrails_ok": decision.guardrails_ok,
        },
        "projected_impact": projected,
    }

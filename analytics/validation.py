"""Experiment health checks.

These run before anyone is allowed to read the result. A trustworthy A/B
readout depends on the randomisation actually having worked, and that is a
claim you verify rather than assume.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import Engine

from analytics.db import get_engine, read_sql
from analytics.logging_config import get_logger
from analytics.statistical_tests import sample_ratio_mismatch, two_proportion_ztest

log = get_logger(__name__)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str
    severity: str = "error"  # error | warning

    @property
    def symbol(self) -> str:
        if self.passed:
            return "PASS"
        return "FAIL" if self.severity == "error" else "WARN"


def check_single_variant_per_user(engine: Engine, experiment_id: int) -> Check:
    """A user must never be exposed to both experiences."""
    offenders = read_sql(
        """
        SELECT COUNT(*) AS n FROM (
            SELECT user_id
            FROM experiment_sessions
            WHERE experiment_id = :eid
            GROUP BY user_id
            HAVING COUNT(DISTINCT variant) > 1
        ) t
        """,
        {"eid": experiment_id}, engine,
    )["n"].iloc[0]
    return Check(
        name="one variant per user",
        passed=offenders == 0,
        detail=(
            "No user appears in both variants."
            if offenders == 0
            else f"{offenders:,} users were exposed to both variants — the "
                 "experiment is contaminated and cannot be read."
        ),
    )


def check_sample_ratio(engine: Engine, experiment_id: int) -> tuple[Check, dict]:
    counts = read_sql(
        """
        SELECT
            COUNT(*) FILTER (WHERE variant = 'A') AS control,
            COUNT(*) FILTER (WHERE variant = 'B') AS treatment
        FROM experiment_users
        WHERE experiment_id = :eid
        """,
        {"eid": experiment_id}, engine,
    ).iloc[0]

    srm = sample_ratio_mismatch(int(counts["control"]), int(counts["treatment"]))
    detail = (
        f"{srm.control_units:,} control / {srm.treatment_units:,} treatment "
        f"({srm.observed_ratio:.3%} treatment), chi-square p = {srm.p_value:.3f}."
    )
    if srm.mismatch_detected:
        detail += " Split deviates further from 50/50 than chance explains."
    return Check("sample ratio mismatch", not srm.mismatch_detected, detail), srm.to_dict()


def check_covariate_balance(engine: Engine, experiment_id: int) -> list[Check]:
    """Pre-exposure attributes should be balanced across arms.

    Device, traffic source and listing price are all determined before the
    variant can influence anything, so a real imbalance would point at a
    randomisation bug rather than a treatment effect.
    """
    checks: list[Check] = []

    shares = read_sql(
        """
        SELECT variant, device, COUNT(*) AS sessions
        FROM experiment_sessions
        WHERE experiment_id = :eid
        GROUP BY variant, device
        """,
        {"eid": experiment_id}, engine,
    )
    pivot = shares.pivot(index="device", columns="variant", values="sessions").fillna(0)
    share = pivot / pivot.sum()
    max_drift = float((share["B"] - share["A"]).abs().max())
    checks.append(Check(
        name="device mix balance",
        passed=max_drift < 0.01,
        detail=f"Largest device share difference between arms: {max_drift:.3%}.",
        severity="warning",
    ))

    price = read_sql(
        """
        SELECT
            s.variant,
            AVG(l.price)       AS mean_price,
            STDDEV_SAMP(l.price) AS sd_price,
            COUNT(*)           AS n
        FROM experiment_sessions s
        JOIN listings l ON l.listing_id = s.listing_id
        WHERE s.experiment_id = :eid
        GROUP BY s.variant
        """,
        {"eid": experiment_id}, engine,
    ).set_index("variant")

    if {"A", "B"}.issubset(price.index):
        a, b = price.loc["A"], price.loc["B"]
        pooled_sd = float(((a["sd_price"] ** 2 + b["sd_price"] ** 2) / 2) ** 0.5)
        smd = abs(float(b["mean_price"]) - float(a["mean_price"])) / pooled_sd
        checks.append(Check(
            name="listing price balance",
            passed=smd < 0.05,
            detail=(
                f"Mean nightly price GBP {float(a['mean_price']):.2f} control vs "
                f"GBP {float(b['mean_price']):.2f} treatment "
                f"(standardised difference {smd:.4f})."
            ),
            severity="warning",
        ))
    return checks


def check_funnel_monotonicity(engine: Engine, experiment_id: int) -> Check:
    """Each funnel step must be a subset of the one before it."""
    bad = read_sql(
        """
        SELECT
            COUNT(*) FILTER (WHERE started_checkout AND NOT clicked_cta) AS skipped_cta,
            COUNT(*) FILTER (WHERE converted AND NOT started_checkout)   AS skipped_checkout
        FROM experiment_results
        WHERE experiment_id = :eid
        """,
        {"eid": experiment_id}, engine,
    ).iloc[0]
    total = int(bad["skipped_cta"]) + int(bad["skipped_checkout"])
    return Check(
        name="funnel ordering",
        passed=total == 0,
        detail=(
            "Every checkout follows a CTA click and every booking follows a checkout."
            if total == 0
            else f"{total:,} sessions skip a funnel step."
        ),
    )


def check_bookings_consistent(engine: Engine, experiment_id: int) -> Check:
    """Every booking_completed event must have exactly one booking row."""
    row = read_sql(
        """
        WITH booked_sessions AS (
            SELECT DISTINCT e.session_id
            FROM experiment_events e
            JOIN experiment_sessions s ON s.session_id = e.session_id
            WHERE e.event_type = 'booking_completed' AND s.experiment_id = :eid
        )
        SELECT
            (SELECT COUNT(*) FROM booked_sessions)                       AS events,
            (SELECT COUNT(*) FROM bookings b
             JOIN experiment_sessions s ON s.session_id = b.session_id
             WHERE s.experiment_id = :eid)                               AS bookings,
            (SELECT COUNT(*) FROM booked_sessions bs
             LEFT JOIN bookings b ON b.session_id = bs.session_id
             WHERE b.booking_id IS NULL)                                 AS orphan_events
        """,
        {"eid": experiment_id}, engine,
    ).iloc[0]
    ok = int(row["events"]) == int(row["bookings"]) and int(row["orphan_events"]) == 0
    return Check(
        name="events match bookings",
        passed=ok,
        detail=(
            f"{int(row['bookings']):,} bookings reconcile with "
            f"{int(row['events']):,} booking_completed events."
        ),
    )


def check_aa_on_pre_exposure_metric(engine: Engine, experiment_id: int) -> Check:
    """An A/A-style sanity test on something the treatment cannot affect.

    The share of sessions arriving on mobile is fixed before a variant is even
    rendered. If that differs significantly between arms, the randomisation is
    suspect regardless of what the primary metric says.
    """
    row = read_sql(
        """
        SELECT
            COUNT(*) FILTER (WHERE variant = 'A')                        AS n_a,
            COUNT(*) FILTER (WHERE variant = 'B')                        AS n_b,
            COUNT(*) FILTER (WHERE variant = 'A' AND device = 'mobile')  AS mobile_a,
            COUNT(*) FILTER (WHERE variant = 'B' AND device = 'mobile')  AS mobile_b
        FROM experiment_sessions
        WHERE experiment_id = :eid
        """,
        {"eid": experiment_id}, engine,
    ).iloc[0]

    test = two_proportion_ztest(
        control_conversions=int(row["mobile_a"]), control_visitors=int(row["n_a"]),
        treatment_conversions=int(row["mobile_b"]), treatment_visitors=int(row["n_b"]),
    )
    return Check(
        name="A/A check on mobile share",
        passed=test.p_value >= 0.01,
        detail=(
            f"Mobile share {test.control_rate:.2%} vs {test.treatment_rate:.2%}, "
            f"p = {test.p_value:.3f}."
        ),
        severity="warning",
    )


def run(experiment_id: int = 1, engine: Engine | None = None) -> tuple[list[Check], dict]:
    engine = engine or get_engine()
    srm_check, srm_payload = check_sample_ratio(engine, experiment_id)
    checks = [
        check_single_variant_per_user(engine, experiment_id),
        srm_check,
        check_funnel_monotonicity(engine, experiment_id),
        check_bookings_consistent(engine, experiment_id),
        check_aa_on_pre_exposure_metric(engine, experiment_id),
        *check_covariate_balance(engine, experiment_id),
    ]
    return checks, srm_payload


def format_report(checks: list[Check]) -> str:
    width = max(len(c.name) for c in checks) + 2
    lines = ["", "EXPERIMENT VALIDATION", "-" * 72]
    for check in checks:
        lines.append(f"  {check.symbol:<5} {check.name:<{width}} {check.detail}")
    failures = [c for c in checks if not c.passed and c.severity == "error"]
    warnings = [c for c in checks if not c.passed and c.severity == "warning"]
    lines.append("-" * 72)
    lines.append(
        f"  {len(checks) - len(failures) - len(warnings)}/{len(checks)} passed, "
        f"{len(warnings)} warning(s), {len(failures)} failure(s)"
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate experiment integrity")
    parser.add_argument("--experiment-id", type=int, default=1)
    args = parser.parse_args()
    checks, _ = run(args.experiment_id)
    print(format_report(checks))
    if any(not c.passed and c.severity == "error" for c in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

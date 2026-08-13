"""Command-line experiment readout.

Prints exactly what the dashboard shows, computed from the database. If this
disagrees with the UI, the UI is wrong.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from analytics.db import get_engine, ping, read_query
from analytics.experiment_service import analyse
from analytics.logging_config import get_logger
from analytics.power_analysis import minimum_detectable_effect
from analytics.validation import format_report, run as run_validation

log = get_logger(__name__)

RULE = "=" * 74
THIN = "-" * 74


def _pct(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:.{digits}%}"


def _p(value: float) -> str:
    """Never print a p-value as 0.0000."""
    return f"{value:.2e}" if value < 1e-4 else f"{value:.4f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Print the full experiment readout")
    parser.add_argument("--experiment-id", type=int, default=1)
    parser.add_argument("--segment", default="device",
                        choices=["device", "traffic_source", "neighbourhood", "room_type"])
    args = parser.parse_args()

    # Windows consoles default to a legacy code page that mangles the pound
    # sign and any box-drawing characters.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    engine = get_engine()
    if not ping(engine):
        raise SystemExit("PostgreSQL unreachable. Try `docker compose up -d db`.")

    eid = args.experiment_id
    result = analyse(eid, engine=engine)
    test = result["statistics"]["primary"]
    decision = result["decision"]

    print(RULE)
    print(f"  StayLab | {result['experiment']['experiment_key']} | "
          f"{result['experiment']['name']}")
    print(f"  {result['experiment']['status'].upper()} | "
          f"{result['experiment']['users']:,} users | "
          f"{result['experiment']['sessions']:,} sessions | "
          f"{result['experiment']['duration_days']} days")
    print(RULE)

    checks, _ = run_validation(eid, engine)
    print(format_report(checks))

    print()
    print("PRIMARY METRIC - booking conversion (per randomised user)")
    print(THIN)
    print(f"  Control A      {test['control_rate']:.2%}   "
          f"({test['control_conversions']:,} / {test['control_visitors']:,})")
    print(f"  Treatment B    {test['treatment_rate']:.2%}   "
          f"({test['treatment_conversions']:,} / {test['treatment_visitors']:,})")
    print()
    print(f"  Absolute uplift    {test['absolute_uplift'] * 100:+.2f} pp")
    print(f"  Relative uplift    {test['relative_uplift']:+.2%}")
    ci = test["confidence_interval"]
    print(f"  95% CI (absolute)  [{ci[0] * 100:+.2f} pp, {ci[1] * 100:+.2f} pp]")
    rci = test["relative_confidence_interval"]
    print(f"  95% CI (relative)  [{rci[0]:+.2%}, {rci[1]:+.2%}]")
    print(f"  z / p              {test['z_score']:.3f} / {_p(test['p_value'])}")
    print(f"  Observed power     {test['observed_power']:.1%}")

    mde = minimum_detectable_effect(test["control_rate"], test["control_visitors"])
    print(f"  MDE at this n      {mde['mde_absolute'] * 100:.2f} pp "
          f"({mde['mde_relative']:+.2%} relative)")

    print()
    print("SECONDARY METRICS")
    print(THIN)
    secondary = pd.DataFrame(result["secondary_metrics"])
    if not secondary.empty:
        for _, row in secondary.iterrows():
            fmt = "{:.2%}" if row["format"] == "percent" else "£{:,.2f}"
            print(f"  {row['label']:<26} "
                  f"{fmt.format(row['control_value']):>12} -> "
                  f"{fmt.format(row['treatment_value']):>12}   "
                  f"{row['relative_change']:+.2%}")

    print()
    print("GUARDRAILS")
    print(THIN)
    for g in result["guardrails"]:
        status = "BREACH" if g["breached"] else "ok"
        print(f"  {status:<7} {g['label']:<26} "
              f"{g['control_value']:.4f} -> {g['treatment_value']:.4f}   "
              f"{g['relative_change']:+.2%}")

    print()
    print("FUNNEL")
    print(THIN)
    funnel = read_query("funnel", {"experiment_id": eid}, engine)
    for _, row in funnel.iterrows():
        lift = (_pct(row["step_relative_lift"])
                if pd.notna(row["step_relative_lift"]) else "-")
        print(f"  {row['step']:<20} "
              f"{_pct(row['control_step_rate']):>9} -> {_pct(row['treatment_step_rate']):>9}"
              f"   {lift:>10}")

    print()
    print(f"SEGMENTS - {args.segment}")
    print(THIN)
    segments = read_query(
        "segmentation",
        {"experiment_id": eid, "segment_type": args.segment, "row_limit": 12},
        engine,
    )
    print(f"  {'Segment':<26}{'Control':>10}{'Treatment':>12}{'Lift':>10}{'Sessions':>11}")
    for _, row in segments.iterrows():
        flag = " *" if row["low_sample"] else ""
        print(f"  {str(row['segment_value'])[:24]:<26}"
              f"{_pct(row['control_rate'], 2):>10}"
              f"{_pct(row['treatment_rate'], 2):>12}"
              f"{_pct(row['relative_lift'], 1):>10}"
              f"{int(row['sessions']):>11,}{flag}")
    if segments["low_sample"].any():
        print("  * underpowered segment — lift is not reliable")

    print()
    print("DECISION")
    print(THIN)
    print(f"  {decision['verdict'].upper()} - {decision['headline']}")
    for line in decision["rationale"]:
        print(f"    - {line}")
    print(f"  Recommendation: {decision['decision'].replace('_', ' ').upper()}")

    impact = result["projected_impact"]
    if impact["annualised_revenue_delta"] is not None:
        print()
        print(f"  Incremental gross bookings (annualised)  "
              f"£{impact['annualised_gross_booking_delta']:,.0f}")
        print(f"  Platform revenue at {impact['platform_take_rate']:.0%} take rate  "
              f"£{impact['annualised_revenue_delta']:,.0f}")
        print(f"    {impact['basis']}")
    print(RULE)


if __name__ == "__main__":
    main()

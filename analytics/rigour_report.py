"""Write the advanced statistics report and the A/A and A/B Monte Carlo checks.

    python -m analytics.rigour_report --sims 200 --out reports/rigour

Each simulation regenerates the whole experiment from the real listings with a new
seed. A/A runs set every treatment effect to zero, so any "significant" result is
a false positive.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import platform
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from analytics.advanced_stats import (
    covariate_matrix,
    cuped,
    daily_looks,
    full_report,
    msprt_pvalues,
    user_frame,
)
from analytics.config import EXPERIMENT, PROCESSED_DIR
from analytics.generate_experiment import generate
from analytics.statistical_tests import two_proportion_ztest

ALPHA = 0.05
_LISTINGS: pd.DataFrame | None = None


def _listings() -> pd.DataFrame:
    global _LISTINGS
    if _LISTINGS is None:
        _LISTINGS = pd.read_parquet(PROCESSED_DIR / "listings.parquet")
    return _LISTINGS


def one_sim(args: tuple[int, float]) -> dict:
    """``scale`` multiplies every treatment effect: 0 is an A/A test, 1 is EXP-024 as designed."""
    seed, scale = args
    cfg = dataclasses.replace(
        EXPERIMENT,
        treatment_logit_cta=EXPERIMENT.treatment_logit_cta * scale,
        treatment_logit_checkout=EXPERIMENT.treatment_logit_checkout * scale,
        treatment_logit_booking=EXPERIMENT.treatment_logit_booking * scale,
    )
    import logging

    logging.disable(logging.INFO)
    users = user_frame(generate(_listings(), config=cfg, seed=seed), _listings())
    looks = daily_looks(users)
    naive = [
        two_proportion_ztest(int(r.conv_a), int(r.n_a), int(r.conv_b), int(r.n_b)).p_value
        for r in looks.itertuples()
    ]
    av = msprt_pvalues(*(looks[c].to_numpy(dtype=float) for c in ("conv_a", "n_a", "conv_b", "n_b")))
    c = cuped(users["converted"].to_numpy(dtype=float), covariate_matrix(users), users["treat"].to_numpy())
    return {
        "seed": seed,
        "effect_scale": scale,
        "final_p": naive[-1],
        "any_peek_p": min(naive),
        "always_valid_final_p": float(av[-1]),
        "raw_estimate": c["unadjusted"]["estimate"],
        "cuped_estimate": c["adjusted"]["estimate"],
        "raw_se": c["unadjusted"]["se"],
        "cuped_se": c["adjusted"]["se"],
        "raw_p": c["unadjusted"]["p_value"],
        "cuped_p": c["adjusted"]["p_value"],
    }


def summarise(rows: list[dict]) -> dict:
    df = pd.DataFrame(rows)

    def rate(col: str) -> dict:
        k = int((df[col] < ALPHA).sum())
        n = len(df)
        se = (k / n * (1 - k / n) / n) ** 0.5
        return {"rate": k / n, "count": k, "n": n, "approx_95_ci": [max(0.0, k / n - 1.96 * se), min(1.0, k / n + 1.96 * se)]}

    return {
        "simulations": len(df),
        "final_look_z_test": rate("final_p"),
        "naive_peeking_14_daily_looks": rate("any_peek_p"),
        "always_valid_msprt": rate("always_valid_final_p"),
        "cuped_test": rate("cuped_p"),
        "raw_estimate_sd_across_sims": float(df["raw_estimate"].std()),
        "cuped_estimate_sd_across_sims": float(df["cuped_estimate"].std()),
        "mean_raw_se": float(df["raw_se"].mean()),
        "mean_cuped_se": float(df["cuped_se"].mean()),
        "mean_raw_estimate": float(df["raw_estimate"].mean()),
        "mean_cuped_estimate": float(df["cuped_estimate"].mean()),
    }


def plots(report: dict, aa: list[dict], ab: list[dict], out: Path) -> None:
    """``ab`` is the reduced effect scenario, where the power differences are visible."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    looks = report["sequential"]["looks"]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.semilogy([x["day"] + 1 for x in looks], [x["naive_p"] for x in looks], "o-", label="naive z-test p")
    ax.semilogy([x["day"] + 1 for x in looks], [x["always_valid_p"] for x in looks], "s-", label="always valid p (mSPRT)")
    ax.axhline(ALPHA, color="grey", ls="--", label="alpha 0.05")
    ax.set_xlabel("day of experiment")
    ax.set_ylabel("p-value (log scale)")
    ax.set_title("EXP-024: daily looks")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "sequential_pvalues.png", dpi=120)
    plt.close(fig)

    s_aa, s_ab = summarise(aa), summarise(ab)
    labels = ["final look only", "peek daily (naive)", "mSPRT"]
    keys = ["final_look_z_test", "naive_peeking_14_daily_looks", "always_valid_msprt"]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    axes[0].bar(labels, [s_aa[k]["rate"] for k in keys], color=["#4c72b0", "#c44e52", "#55a868"])
    axes[0].axhline(ALPHA, color="grey", ls="--")
    axes[0].set_title(f"A/A false positive rate ({s_aa['simulations']} sims)")
    axes[1].bar(labels, [s_ab[k]["rate"] for k in keys], color=["#4c72b0", "#c44e52", "#55a868"])
    axes[1].set_title(f"Power at 40% of the designed effect ({s_ab['simulations']} sims)")
    for a in axes:
        a.tick_params(axis="x", labelsize=8)
    fig.tight_layout()
    fig.savefig(out / "monte_carlo_error_rates.png", dpi=120)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=200)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--out", type=Path, default=Path("reports/rigour"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    import logging

    logging.disable(logging.INFO)
    t0 = time.time()
    report = full_report(generate(_listings()), _listings())
    (args.out / "exp024_advanced_stats.json").write_text(json.dumps(report, indent=2, default=float))
    seeds = list(range(1000, 1000 + args.sims))
    with ProcessPoolExecutor(args.workers) as ex:
        aa = list(ex.map(one_sim, [(s, 0.0) for s in seeds]))
        ab = list(ex.map(one_sim, [(s, 1.0) for s in seeds]))
        ab_small = list(ex.map(one_sim, [(s, 0.4) for s in seeds]))
    pd.DataFrame(aa + ab + ab_small).to_csv(args.out / "monte_carlo_runs.csv", index=False)
    mc = {
        "aa_no_effect": summarise(aa),
        "ab_designed_effect": summarise(ab),
        "ab_40pct_effect": summarise(ab_small),
        "seeds": [seeds[0], seeds[-1]],
        "alpha": ALPHA,
        "msprt_tau": 0.01,
        "runtime_seconds": round(time.time() - t0, 1),
        "hardware": {"machine": platform.machine(), "python": platform.python_version()},
    }
    (args.out / "monte_carlo_summary.json").write_text(json.dumps(mc, indent=2))
    plots(report, aa, ab_small, args.out)
    print(json.dumps(mc, indent=1))


if __name__ == "__main__":
    main()

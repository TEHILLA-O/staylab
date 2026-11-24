"""Extra rigour for the EXP-024 readout.

Adds the checks a reviewer usually asks for after the headline z-test:

* power and sample size planning before launch
* CUPED style regression adjustment with pre-assignment covariates
* bootstrap confidence intervals for relative lift and revenue per user
* sample ratio mismatch on the whole test and on every day, with Holm correction
* multiple testing correction (Holm and Benjamini-Hochberg) across segments
* an always-valid sequential test (mSPRT) next to naive daily peeking

Works straight from the simulator output, so no database is needed.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from analytics.power_analysis import minimum_detectable_effect, required_sample_size
from analytics.statistical_tests import sample_ratio_mismatch, two_proportion_ztest

# --------------------------------------------------------------------------
# User level frame
# --------------------------------------------------------------------------


def user_frame(data: dict[str, pd.DataFrame], listings: pd.DataFrame) -> pd.DataFrame:
    """One row per randomised user with outcome and pre-assignment covariates.

    Covariates come from the first session only: the device, the traffic source
    and the observable attributes of the first listing viewed. All of these are
    known before the treatment page renders, so adjusting for them cannot absorb
    the treatment effect.
    """
    sessions = data["sessions"]
    bookings = data["bookings"]
    first = sessions.sort_values(["user_id", "session_started_at"]).groupby("user_id").first()
    revenue = (
        bookings.merge(sessions[["session_id", "user_id"]], on="session_id")
        .groupby("user_id")["booking_value"]
        .sum()
    )
    conv = sessions.groupby("user_id")["converted"].max()
    lst = listings.set_index("listing_id")
    lf = lst.loc[first["listing_id"].to_numpy()]
    users = pd.DataFrame(
        {
            "variant": first["variant"].to_numpy(),
            "converted": conv.loc[first.index].astype(int).to_numpy(),
            "revenue": revenue.reindex(first.index).fillna(0.0).to_numpy(),
            "day": first["day_index"].to_numpy(),
            "device": first["device"].to_numpy(),
            "traffic_source": first["traffic_source"].to_numpy(),
            "neighbourhood": lf["neighbourhood"].to_numpy(),
            "rating": lf["review_scores_rating"].fillna(lf["review_scores_rating"].median()).to_numpy(),
            "has_rating": lf["has_review_score"].astype(float).to_numpy(),
            "log_price_ratio": np.log(
                np.clip(lf["price_vs_neighbourhood"].fillna(1.0).to_numpy(dtype=float), 0.2, 5.0)
            ),
            "instant_bookable": lf["instant_bookable"].astype(float).to_numpy(),
            "superhost": lf["host_is_superhost"].astype(float).to_numpy(),
            "room_type": lf["room_type"].to_numpy(),
        },
        index=first.index,
    )
    users["treat"] = (users["variant"] == "B").astype(int)
    return users


COVARIATES_NUMERIC = ["rating", "has_rating", "log_price_ratio", "instant_bookable", "superhost"]
COVARIATES_CATEGORICAL = ["device", "traffic_source", "room_type"]


def covariate_matrix(users: pd.DataFrame) -> np.ndarray:
    dummies = pd.get_dummies(users[COVARIATES_CATEGORICAL], drop_first=True, dtype=float)
    x = pd.concat([users[COVARIATES_NUMERIC].astype(float), dummies], axis=1).to_numpy()
    return x - x.mean(axis=0)


# --------------------------------------------------------------------------
# CUPED / regression adjustment
# --------------------------------------------------------------------------


def diff_in_means(y: np.ndarray, treat: np.ndarray, alpha: float = 0.05) -> dict[str, float]:
    yt, yc = y[treat == 1], y[treat == 0]
    diff = yt.mean() - yc.mean()
    se = math.sqrt(yt.var(ddof=1) / len(yt) + yc.var(ddof=1) / len(yc))
    z = stats.norm.ppf(1 - alpha / 2)
    return {
        "estimate": float(diff),
        "se": float(se),
        "ci_low": float(diff - z * se),
        "ci_high": float(diff + z * se),
        "p_value": float(2 * stats.norm.sf(abs(diff / se))),
    }


def cuped(y: np.ndarray, x: np.ndarray, treat: np.ndarray) -> dict[str, Any]:
    """CUPED with several pre-assignment covariates.

    theta is fitted on the pooled sample by least squares, then
    y_adj = y - (x - mean(x)) @ theta and the usual difference in means is taken.
    With centred covariates this keeps the estimate unbiased under randomisation.
    """
    theta, *_ = np.linalg.lstsq(x, y - y.mean(), rcond=None)
    y_adj = y - x @ theta
    raw = diff_in_means(y, treat)
    adj = diff_in_means(y_adj, treat)
    return {
        "unadjusted": raw,
        "adjusted": adj,
        "variance_reduction": float(1 - y_adj.var() / y.var()),
        "ci_width_ratio": float(adj["se"] / raw["se"]),
        "equivalent_sample_size_gain": float((raw["se"] / adj["se"]) ** 2 - 1),
    }


# --------------------------------------------------------------------------
# Bootstrap
# --------------------------------------------------------------------------


def bootstrap_lift(
    users: pd.DataFrame, n_boot: int = 2000, seed: int = 0
) -> dict[str, dict[str, float]]:
    rng = np.random.default_rng(seed)
    out: dict[str, dict[str, float]] = {}
    groups = {v: users.loc[users["variant"] == v] for v in ("A", "B")}
    for metric in ("converted", "revenue"):
        a = groups["A"][metric].to_numpy(dtype=float)
        b = groups["B"][metric].to_numpy(dtype=float)
        rel, absd = [], []
        for _ in range(n_boot):
            ma = a[rng.integers(0, len(a), len(a))].mean()
            mb = b[rng.integers(0, len(b), len(b))].mean()
            absd.append(mb - ma)
            rel.append(mb / ma - 1)
        out[metric] = {
            "control_mean": float(a.mean()),
            "treatment_mean": float(b.mean()),
            "absolute_diff": float(b.mean() - a.mean()),
            "absolute_ci": [float(np.quantile(absd, 0.025)), float(np.quantile(absd, 0.975))],
            "relative_lift": float(b.mean() / a.mean() - 1),
            "relative_ci": [float(np.quantile(rel, 0.025)), float(np.quantile(rel, 0.975))],
            "n_boot": n_boot,
        }
    return out


# --------------------------------------------------------------------------
# SRM and multiple testing
# --------------------------------------------------------------------------


def srm_report(users: pd.DataFrame) -> dict[str, Any]:
    counts = users["variant"].value_counts()
    overall = sample_ratio_mismatch(int(counts.get("A", 0)), int(counts.get("B", 0)))
    daily = []
    for day, g in users.groupby("day"):
        c = g["variant"].value_counts()
        check = sample_ratio_mismatch(int(c.get("A", 0)), int(c.get("B", 0)))
        daily.append({"day": int(day), "A": check.control_units, "B": check.treatment_units,
                      "p_value": check.p_value})
    holm = multipletests([d["p_value"] for d in daily], alpha=0.001, method="holm")
    for d, p_adj, rej in zip(daily, holm[1], holm[0]):
        d["p_holm"] = float(p_adj)
        d["flag"] = bool(rej)
    return {"overall": overall.to_dict(), "daily": daily,
            "any_day_flagged": bool(any(d["flag"] for d in daily))}


def segment_tests(users: pd.DataFrame, column: str, min_users: int = 500) -> list[dict[str, Any]]:
    rows = []
    for value, g in users.groupby(column):
        a, b = g[g["variant"] == "A"], g[g["variant"] == "B"]
        if min(len(a), len(b)) < min_users // 2:
            continue
        t = two_proportion_ztest(int(a["converted"].sum()), len(a), int(b["converted"].sum()), len(b))
        rows.append({"segment": f"{column}={value}", "users": int(len(g)),
                     "control_rate": t.control_rate, "treatment_rate": t.treatment_rate,
                     "absolute_uplift": t.absolute_uplift, "p_value": t.p_value})
    return rows


def multiple_testing(users: pd.DataFrame, alpha: float = 0.05) -> dict[str, Any]:
    rows = []
    for col in ("device", "traffic_source", "room_type", "neighbourhood"):
        rows.extend(segment_tests(users, col))
    p = [r["p_value"] for r in rows]
    holm = multipletests(p, alpha=alpha, method="holm")
    bh = multipletests(p, alpha=alpha, method="fdr_bh")
    for r, ph, pb in zip(rows, holm[1], bh[1]):
        r["p_holm"] = float(ph)
        r["p_bh"] = float(pb)
    return {
        "tests": len(rows),
        "significant_unadjusted": int(sum(x < alpha for x in p)),
        "significant_holm": int(holm[0].sum()),
        "significant_bh": int(bh[0].sum()),
        "segments": rows,
    }


# --------------------------------------------------------------------------
# Sequential testing
# --------------------------------------------------------------------------


def msprt_pvalues(
    conv_a: np.ndarray, n_a: np.ndarray, conv_b: np.ndarray, n_b: np.ndarray, tau: float = 0.01
) -> np.ndarray:
    """Always-valid p-values for a difference in proportions (Johari et al., 2017).

    Uses a normal mixture N(0, tau^2) over the true difference and a plug-in
    variance. The returned sequence can be checked after every look without
    inflating the false positive rate.
    """
    pa, pb = conv_a / n_a, conv_b / n_b
    diff = pb - pa
    v = pa * (1 - pa) / n_a + pb * (1 - pb) / n_b
    v = np.maximum(v, 1e-12)
    t2 = tau**2
    log_lr = 0.5 * np.log(v / (v + t2)) + diff**2 * t2 / (2 * v * (v + t2))
    p = np.minimum(1.0, np.exp(-log_lr))
    return np.minimum.accumulate(p)


def daily_looks(users: pd.DataFrame) -> pd.DataFrame:
    g = users.groupby(["day", "variant"])["converted"].agg(["sum", "count"]).unstack("variant")
    g = g.sort_index().cumsum()
    return pd.DataFrame(
        {"conv_a": g[("sum", "A")], "n_a": g[("count", "A")],
         "conv_b": g[("sum", "B")], "n_b": g[("count", "B")]}
    )


def sequential_readout(users: pd.DataFrame, alpha: float = 0.05, tau: float = 0.01) -> dict[str, Any]:
    looks = daily_looks(users)
    naive = []
    for row in looks.itertuples():
        t = two_proportion_ztest(int(row.conv_a), int(row.n_a), int(row.conv_b), int(row.n_b))
        naive.append(t.p_value)
    av = msprt_pvalues(*(looks[c].to_numpy(dtype=float) for c in ("conv_a", "n_a", "conv_b", "n_b")), tau=tau)
    first_naive = next((i for i, p in enumerate(naive) if p < alpha), None)
    first_av = next((i for i, p in enumerate(av) if p < alpha), None)
    return {
        "tau": tau,
        "looks": [
            {"day": int(d), "users": int(r.n_a + r.n_b), "naive_p": float(np_), "always_valid_p": float(ap)}
            for (d, r), np_, ap in zip(looks.iterrows(), naive, av)
        ],
        "first_day_naive_significant": first_naive,
        "first_day_always_valid_significant": first_av,
    }


# --------------------------------------------------------------------------
# Power planning
# --------------------------------------------------------------------------


def power_table(baseline: float, daily_users_per_variant: float) -> list[dict[str, Any]]:
    rows = []
    for mde in (0.02, 0.05, 0.10, 0.15):
        r = required_sample_size(baseline, mde)
        rows.append({
            "mde_relative": mde,
            "required_per_variant": r.required_per_variant,
            "days_at_observed_traffic": round(r.required_per_variant / daily_users_per_variant, 1),
        })
    return rows


def full_report(data: dict[str, pd.DataFrame], listings: pd.DataFrame) -> dict[str, Any]:
    users = user_frame(data, listings)
    a = users[users["variant"] == "A"]
    baseline = float(a["converted"].mean())
    days = int(users["day"].max()) + 1
    x = covariate_matrix(users)
    treat = users["treat"].to_numpy()
    return {
        "users": int(len(users)),
        "days": days,
        "power_plan": {
            "baseline_rate": baseline,
            "table": power_table(baseline, len(a) / days),
            "mde_at_observed_n": minimum_detectable_effect(baseline, len(a)),
        },
        "srm": srm_report(users),
        "cuped_conversion": cuped(users["converted"].to_numpy(dtype=float), x, treat),
        "cuped_revenue": cuped(users["revenue"].to_numpy(dtype=float), x, treat),
        "bootstrap": bootstrap_lift(users),
        "multiple_testing": multiple_testing(users),
        "sequential": sequential_readout(users),
    }

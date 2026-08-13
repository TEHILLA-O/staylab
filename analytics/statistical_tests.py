"""Inference on top of the aggregates SQL produces.

SQL answers "what happened". This module answers "is the difference credible,
how large is it, and is that large enough to act on".
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
from scipy import stats
from statsmodels.stats.proportion import (
    confint_proportions_2indep,
    proportion_confint,
    proportions_ztest,
)

Decision = Literal["ship", "iterate", "do_not_ship", "keep_running"]
Verdict = Literal["significant", "inconclusive", "negative"]


@dataclass(frozen=True)
class ProportionTest:
    """Result of a two-proportion comparison, control vs treatment."""

    control_visitors: int
    treatment_visitors: int
    control_conversions: int
    treatment_conversions: int

    control_rate: float
    treatment_rate: float
    control_rate_ci: tuple[float, float]
    treatment_rate_ci: tuple[float, float]

    absolute_uplift: float
    relative_uplift: float
    confidence_interval: tuple[float, float]
    relative_confidence_interval: tuple[float, float]

    z_score: float
    p_value: float
    standard_error: float
    confidence_level: float
    significance_level: float
    statistically_significant: bool
    observed_power: float

    def to_dict(self) -> dict:
        return asdict(self)


def two_proportion_ztest(
    control_conversions: int,
    control_visitors: int,
    treatment_conversions: int,
    treatment_visitors: int,
    *,
    alpha: float = 0.05,
    alternative: str = "two-sided",
) -> ProportionTest:
    """Two-proportion z-test with confidence intervals on both effect scales.

    A two-sided test is the default even though the hypothesis is directional.
    A one-sided test would make a harmful result look like a null result, and
    the guardrail logic needs to be able to see harm.
    """
    for name, value in (
        ("control_visitors", control_visitors),
        ("treatment_visitors", treatment_visitors),
    ):
        if value <= 0:
            raise ValueError(f"{name} must be positive, got {value}")
    if not 0 <= control_conversions <= control_visitors:
        raise ValueError("control_conversions out of range")
    if not 0 <= treatment_conversions <= treatment_visitors:
        raise ValueError("treatment_conversions out of range")

    p_control = control_conversions / control_visitors
    p_treatment = treatment_conversions / treatment_visitors

    z_score, p_value = proportions_ztest(
        count=np.array([treatment_conversions, control_conversions]),
        nobs=np.array([treatment_visitors, control_visitors]),
        alternative=alternative,
    )

    # Unpooled SE for the interval (the pooled SE belongs to the test only).
    se = math.sqrt(
        p_control * (1 - p_control) / control_visitors
        + p_treatment * (1 - p_treatment) / treatment_visitors
    )
    ci_low, ci_high = confint_proportions_2indep(
        count1=treatment_conversions, nobs1=treatment_visitors,
        count2=control_conversions, nobs2=control_visitors,
        method="wald", compare="diff", alpha=alpha,
    )

    absolute = p_treatment - p_control
    relative = absolute / p_control if p_control > 0 else float("nan")
    rel_ci = (
        (ci_low / p_control, ci_high / p_control)
        if p_control > 0
        else (float("nan"), float("nan"))
    )

    control_ci = proportion_confint(control_conversions, control_visitors,
                                    alpha=alpha, method="wilson")
    treatment_ci = proportion_confint(treatment_conversions, treatment_visitors,
                                      alpha=alpha, method="wilson")

    return ProportionTest(
        control_visitors=int(control_visitors),
        treatment_visitors=int(treatment_visitors),
        control_conversions=int(control_conversions),
        treatment_conversions=int(treatment_conversions),
        control_rate=p_control,
        treatment_rate=p_treatment,
        control_rate_ci=(float(control_ci[0]), float(control_ci[1])),
        treatment_rate_ci=(float(treatment_ci[0]), float(treatment_ci[1])),
        absolute_uplift=float(absolute),
        relative_uplift=float(relative),
        confidence_interval=(float(ci_low), float(ci_high)),
        relative_confidence_interval=(float(rel_ci[0]), float(rel_ci[1])),
        z_score=float(z_score),
        p_value=float(p_value),
        standard_error=float(se),
        confidence_level=1 - alpha,
        significance_level=alpha,
        statistically_significant=bool(p_value < alpha),
        observed_power=observed_power(p_control, p_treatment,
                                      control_visitors, treatment_visitors, alpha),
    )


def observed_power(p_control: float, p_treatment: float, n_control: int,
                   n_treatment: int, alpha: float = 0.05) -> float:
    """Power to detect the observed effect at the realised sample sizes."""
    if p_control in (0.0, 1.0) and p_treatment in (0.0, 1.0):
        return float("nan")
    pooled = (p_control * n_control + p_treatment * n_treatment) / (n_control + n_treatment)
    se_null = math.sqrt(pooled * (1 - pooled) * (1 / n_control + 1 / n_treatment))
    se_alt = math.sqrt(
        p_control * (1 - p_control) / n_control
        + p_treatment * (1 - p_treatment) / n_treatment
    )
    if se_alt == 0:
        return float("nan")
    z_crit = stats.norm.ppf(1 - alpha / 2)
    delta = abs(p_treatment - p_control)
    upper = (delta - z_crit * se_null) / se_alt
    lower = (-delta - z_crit * se_null) / se_alt
    return float(stats.norm.cdf(upper) + stats.norm.cdf(lower))


# --------------------------------------------------------------------------
# Continuous metrics (revenue per visitor, average booking value)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MeansTest:
    control_mean: float
    treatment_mean: float
    absolute_uplift: float
    relative_uplift: float
    confidence_interval: tuple[float, float]
    t_statistic: float
    p_value: float
    statistically_significant: bool

    def to_dict(self) -> dict:
        return asdict(self)


def welch_ttest_from_summary(
    control_mean: float, control_sd: float, control_n: int,
    treatment_mean: float, treatment_sd: float, treatment_n: int,
    *, alpha: float = 0.05,
) -> MeansTest:
    """Welch's t-test from group summaries.

    Revenue per visitor is extremely skewed (most visitors spend nothing, a few
    spend thousands), so equal variances cannot be assumed.
    """
    if control_n < 2 or treatment_n < 2:
        raise ValueError("both groups need at least 2 observations")

    se = math.sqrt(control_sd**2 / control_n + treatment_sd**2 / treatment_n)
    diff = treatment_mean - control_mean
    if se == 0:
        return MeansTest(control_mean, treatment_mean, diff, float("nan"),
                         (float("nan"), float("nan")), float("nan"), float("nan"), False)

    df = (control_sd**2 / control_n + treatment_sd**2 / treatment_n) ** 2 / (
        (control_sd**2 / control_n) ** 2 / (control_n - 1)
        + (treatment_sd**2 / treatment_n) ** 2 / (treatment_n - 1)
    )
    t_stat = diff / se
    p_value = 2 * stats.t.sf(abs(t_stat), df)
    margin = stats.t.ppf(1 - alpha / 2, df) * se

    return MeansTest(
        control_mean=float(control_mean),
        treatment_mean=float(treatment_mean),
        absolute_uplift=float(diff),
        relative_uplift=float(diff / control_mean) if control_mean else float("nan"),
        confidence_interval=(float(diff - margin), float(diff + margin)),
        t_statistic=float(t_stat),
        p_value=float(p_value),
        statistically_significant=bool(p_value < alpha),
    )


# --------------------------------------------------------------------------
# Sample ratio mismatch
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SampleRatioCheck:
    control_units: int
    treatment_units: int
    expected_ratio: float
    observed_ratio: float
    chi_square: float
    p_value: float
    mismatch_detected: bool

    def to_dict(self) -> dict:
        return asdict(self)


def sample_ratio_mismatch(control_units: int, treatment_units: int,
                          expected_ratio: float = 0.5,
                          alpha: float = 0.001) -> SampleRatioCheck:
    """Chi-square goodness-of-fit test on the allocation split.

    Uses a strict alpha of 0.001: an SRM flag invalidates the whole experiment,
    so the bar for raising it should be higher than for the primary metric.
    """
    total = control_units + treatment_units
    if total == 0:
        raise ValueError("no units to test")
    expected = [total * (1 - expected_ratio), total * expected_ratio]
    chi2, p_value = stats.chisquare([control_units, treatment_units], f_exp=expected)
    return SampleRatioCheck(
        control_units=int(control_units),
        treatment_units=int(treatment_units),
        expected_ratio=float(expected_ratio),
        observed_ratio=float(treatment_units / total),
        chi_square=float(chi2),
        p_value=float(p_value),
        mismatch_detected=bool(p_value < alpha),
    )


# --------------------------------------------------------------------------
# Decision logic
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExperimentDecision:
    verdict: Verdict
    decision: Decision
    headline: str
    rationale: list[str]
    guardrails_ok: bool


def decide(
    test: ProportionTest,
    *,
    srm: SampleRatioCheck | None = None,
    guardrail_breaches: list[str] | None = None,
    practical_significance_threshold: float = 0.01,
) -> ExperimentDecision:
    """Turn statistics into a recommendation.

    Significance alone is not the decision. A large sample makes trivially
    small effects significant, so the effect also has to clear a practical
    threshold, the confidence interval has to exclude effects too small to be
    worth the engineering cost, and guardrails have to hold.
    """
    breaches = list(guardrail_breaches or [])
    rationale: list[str] = []
    guardrails_ok = not breaches

    def fmt_p(value: float) -> str:
        return f"{value:.2e}" if value < 1e-4 else f"{value:.4f}"

    if srm is not None and srm.mismatch_detected:
        return ExperimentDecision(
            verdict="inconclusive",
            decision="do_not_ship",
            headline="Sample ratio mismatch — results not trustworthy",
            rationale=[
                f"Allocation is {srm.observed_ratio:.2%} treatment against an "
                f"expected {srm.expected_ratio:.0%} (chi-square p = {srm.p_value:.2e}).",
                "A skewed split usually means an assignment or logging bug. "
                "Fix the pipeline and rerun before reading the metrics.",
            ],
            guardrails_ok=False,
        )

    ci_low, ci_high = test.confidence_interval
    rel = test.relative_uplift
    significant = test.statistically_significant
    positive = test.absolute_uplift > 0
    clears_practical_bar = abs(rel) >= practical_significance_threshold

    rationale.append(
        f"Treatment converted at {test.treatment_rate:.2%} against "
        f"{test.control_rate:.2%} for control "
        f"({test.absolute_uplift * 100:+.2f}pp, {rel:+.1%} relative)."
    )
    rationale.append(
        f"95% CI for the absolute difference: "
        f"[{ci_low * 100:+.2f}pp, {ci_high * 100:+.2f}pp]; p = {fmt_p(test.p_value)}."
    )

    if significant and positive and clears_practical_bar and guardrails_ok:
        verdict: Verdict = "significant"
        decision: Decision = "ship"
        headline = "Treatment B is winning — ship it"
        rationale.append(
            "The interval excludes zero, the effect is large enough to matter, "
            "and no guardrail moved against us."
        )
    elif significant and positive and not guardrails_ok:
        verdict, decision = "significant", "iterate"
        headline = "Primary metric up, but a guardrail regressed"
        rationale.append("Guardrail breach: " + "; ".join(breaches))
        rationale.append(
            "Address the regression before rolling out, or ship behind a "
            "holdback and keep monitoring."
        )
    elif significant and positive and not clears_practical_bar:
        verdict, decision = "significant", "iterate"
        headline = "Statistically significant but too small to matter"
        rationale.append(
            f"A {rel:+.1%} relative change is below the "
            f"{practical_significance_threshold:.0%} practical threshold. "
            "Significance here is a function of sample size, not impact."
        )
    elif significant and not positive:
        verdict, decision = "negative", "do_not_ship"
        headline = "Treatment B is losing — do not ship"
        rationale.append(
            "The treatment significantly reduced the primary metric. Roll back "
            "and investigate which step of the funnel regressed."
        )
    else:
        verdict, decision = "inconclusive", "keep_running"
        headline = "Inconclusive — the interval still includes zero"
        rationale.append(
            "We cannot distinguish this result from no effect. Either keep "
            "collecting data until the experiment is powered for the effect "
            "actually on offer, or accept the null and move on."
        )
        if test.observed_power == test.observed_power:  # not NaN
            rationale.append(
                f"Power to detect the observed effect at this sample size: "
                f"{test.observed_power:.0%}."
            )

    if breaches and guardrails_ok is False and decision == "ship":  # defensive
        decision = "iterate"

    return ExperimentDecision(
        verdict=verdict,
        decision=decision,
        headline=headline,
        rationale=rationale,
        guardrails_ok=guardrails_ok,
    )

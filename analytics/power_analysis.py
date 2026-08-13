"""Power and sample-size analysis.

Run before the experiment to size it, and after to state honestly what the
experiment was and was not capable of detecting.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import asdict, dataclass

from scipy import stats
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize


@dataclass(frozen=True)
class PowerResult:
    baseline_rate: float
    mde_relative: float
    mde_absolute: float
    target_rate: float
    alpha: float
    power: float
    effect_size: float
    required_per_variant: int
    required_total: int

    def to_dict(self) -> dict:
        return asdict(self)


def required_sample_size(baseline_rate: float, mde_relative: float = 0.05,
                         alpha: float = 0.05, power: float = 0.80,
                         ratio: float = 1.0) -> PowerResult:
    """Sample size per variant to detect a relative lift with given power."""
    if not 0 < baseline_rate < 1:
        raise ValueError("baseline_rate must be strictly between 0 and 1")
    if mde_relative <= 0:
        raise ValueError("mde_relative must be positive")

    target = baseline_rate * (1 + mde_relative)
    if target >= 1:
        raise ValueError("mde_relative pushes the target rate to or above 1")

    effect = proportion_effectsize(target, baseline_rate)
    n = NormalIndPower().solve_power(
        effect_size=effect, alpha=alpha, power=power, ratio=ratio,
        alternative="two-sided",
    )
    per_variant = int(math.ceil(n))
    return PowerResult(
        baseline_rate=baseline_rate,
        mde_relative=mde_relative,
        mde_absolute=target - baseline_rate,
        target_rate=target,
        alpha=alpha,
        power=power,
        effect_size=float(effect),
        required_per_variant=per_variant,
        required_total=per_variant + int(math.ceil(per_variant * ratio)),
    )


def minimum_detectable_effect(baseline_rate: float, n_per_variant: int,
                              alpha: float = 0.05, power: float = 0.80) -> dict:
    """The smallest effect this sample size could reliably have detected.

    The number to quote when an experiment comes back inconclusive: "we could
    not have seen anything smaller than this" is far more useful than "p > .05".
    """
    if n_per_variant <= 0:
        raise ValueError("n_per_variant must be positive")
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    se = math.sqrt(2 * baseline_rate * (1 - baseline_rate) / n_per_variant)
    absolute = (z_alpha + z_beta) * se
    return {
        "baseline_rate": baseline_rate,
        "n_per_variant": int(n_per_variant),
        "alpha": alpha,
        "power": power,
        "mde_absolute": float(absolute),
        "mde_relative": float(absolute / baseline_rate) if baseline_rate else float("nan"),
    }


def days_to_significance(baseline_rate: float, mde_relative: float,
                         daily_users_per_variant: float, alpha: float = 0.05,
                         power: float = 0.80) -> float:
    """How long the experiment needs to run at the current traffic level."""
    if daily_users_per_variant <= 0:
        raise ValueError("daily_users_per_variant must be positive")
    required = required_sample_size(baseline_rate, mde_relative, alpha, power)
    return required.required_per_variant / daily_users_per_variant


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample size / power analysis")
    parser.add_argument("--baseline", type=float, default=0.098)
    parser.add_argument("--mde", type=float, default=0.05, help="relative MDE, e.g. 0.05")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--power", type=float, default=0.80)
    parser.add_argument("--daily-users", type=float, default=None)
    args = parser.parse_args()

    result = required_sample_size(args.baseline, args.mde, args.alpha, args.power)
    print(f"Baseline conversion      {result.baseline_rate:.2%}")
    print(f"Relative MDE             {result.mde_relative:+.1%}")
    print(f"Absolute MDE             {result.mde_absolute * 100:+.2f}pp")
    print(f"Target rate              {result.target_rate:.2%}")
    print(f"alpha / power            {result.alpha} / {result.power}")
    print(f"Required per variant     {result.required_per_variant:,}")
    print(f"Required total           {result.required_total:,}")
    if args.daily_users:
        days = days_to_significance(args.baseline, args.mde, args.daily_users,
                                    args.alpha, args.power)
        print(f"Days at {args.daily_users:,.0f}/variant/day  {days:.1f}")


if __name__ == "__main__":
    main()

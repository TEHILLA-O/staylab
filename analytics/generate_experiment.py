"""Generate the SIMULATED randomised experiment for StayLab.

Inside Airbnb publishes listing and calendar data. It does not publish
user-level experiment assignments or funnel events, and comparing (say)
instant_bookable = true against false would not be an experiment at all
because hosts were never randomised into those groups.

So this module builds an explicit randomised layer on top of the real listing
attributes:

    users     -> randomised once, 50/50, into A (control) or B (treatment)
    sessions  -> each session views one real London listing
    funnel    -> listing_view -> cta_click -> checkout_started ->
                 booking_completed, with per-step probabilities driven by the
                 listing's real characteristics plus session context
    bookings  -> value derived from the listing's real calendar pricing

The treatment effect is a small, configurable, additive shift on the logit
scale, applied at the steps a "show the total price, clearer Reserve button"
redesign would plausibly influence. Nothing about the final measured result is
hard-coded: the pipeline measures whatever the simulation produced.

Everything is driven by one seed (config.EXPERIMENT.seed) and is reproducible.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from analytics.config import (
    DEVICE_WEIGHTS,
    DEVICES,
    EXPERIMENT,
    PROCESSED_DIR,
    TRAFFIC_SOURCES,
    TRAFFIC_WEIGHTS,
    ExperimentConfig,
)
from analytics.logging_config import get_logger

log = get_logger(__name__)


def logit(p: float | np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    return np.log(p / (1.0 - p))


def expit(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


# --------------------------------------------------------------------------
# Effect sizes. Kept as named tables so the model is auditable rather than a
# wall of magic numbers inside the simulation loop.
# --------------------------------------------------------------------------

ROOM_TYPE_EFFECT = {
    "Entire home/apt": 0.10,
    "Private room": 0.00,
    "Hotel room": -0.06,
    "Shared room": -0.32,
}

DEVICE_EFFECT = {
    # Mobile is easy to tap but painful to check out on: the sign flips
    # further down the funnel, which is exactly the kind of pattern segment
    # analysis is supposed to surface.
    "mobile":  {"cta": 0.12, "checkout": -0.24, "booking": -0.16},
    "desktop": {"cta": -0.02, "checkout": 0.10, "booking": 0.12},
    "tablet":  {"cta": -0.08, "checkout": -0.04, "booking": -0.05},
}

TRAFFIC_EFFECT = {
    "direct":         0.32,
    "email":          0.24,
    "organic_search": 0.06,
    "referral":       0.00,
    "paid_search":   -0.09,
    "paid_social":   -0.38,
}

# Sessions per weekday index (Mon=0). Leisure travel browsing peaks Sun-Mon.
WEEKDAY_TRAFFIC = np.array([1.12, 1.05, 1.00, 0.98, 0.92, 0.85, 1.08])
# Weekend browsers convert slightly worse: more casual, less trip-planning.
WEEKDAY_CONVERSION = np.array([0.04, 0.03, 0.01, 0.00, -0.03, -0.06, -0.02])

HOUR_WEIGHTS = np.array([
    0.6, 0.35, 0.22, 0.18, 0.18, 0.28, 0.55, 0.95, 1.25, 1.45, 1.55, 1.6,
    1.62, 1.58, 1.5, 1.45, 1.5, 1.6, 1.75, 1.9, 2.0, 1.75, 1.35, 0.95,
])


def _centre(values: np.ndarray) -> np.ndarray:
    """Remove the mean so configured base rates keep their meaning.

    Without this the covariate block would silently shift the intercept and
    ``base_cta_click`` would no longer be the rate an average session sees.
    """
    return values - values.mean()


# --------------------------------------------------------------------------
# Listing quality signal
# --------------------------------------------------------------------------


def listing_appeal(listings: pd.DataFrame) -> np.ndarray:
    """A per-listing desirability score built from real Inside Airbnb fields."""
    rating = listings["review_scores_rating"].to_numpy(dtype=float)
    has_rating = listings["has_review_score"].to_numpy(dtype=bool)

    rating_effect = np.where(
        has_rating,
        np.clip(0.90 * (np.nan_to_num(rating, nan=4.7) - 4.70), -0.40, 0.26),
        -0.12,  # no reviews yet: less social proof, not a bad listing
    )

    superhost = np.where(listings["host_is_superhost"].to_numpy(dtype=bool), 0.13, 0.0)
    instant = np.where(listings["instant_bookable"].to_numpy(dtype=bool), 0.17, 0.0)

    ratio = listings["price_vs_neighbourhood"].to_numpy(dtype=float)
    ratio = np.clip(np.nan_to_num(ratio, nan=1.0), 0.2, 5.0)
    price_effect = np.clip(-0.38 * np.log(ratio), -0.55, 0.45)

    room = listings["room_type"].map(ROOM_TYPE_EFFECT).fillna(0.0).to_numpy(dtype=float)

    reviews = listings["number_of_reviews"].to_numpy(dtype=float)
    social_proof = np.clip(0.055 * np.log1p(reviews) / np.log(50.0), 0.0, 0.16)

    avail = np.nan_to_num(
        listings["calendar_availability_rate"].to_numpy(dtype=float), nan=0.5
    )
    scarcity = 0.10 * (1.0 - np.clip(avail, 0.0, 1.0))

    return (
        rating_effect + superhost + instant + price_effect
        + room + social_proof + scarcity
    )


def exposure_weights(listings: pd.DataFrame) -> np.ndarray:
    """How likely each listing is to be shown to a visitor.

    Real marketplaces are extremely concentrated: a small share of listings
    absorbs most demand. Weighting by recent review velocity and forward
    availability reproduces that skew instead of sampling uniformly.
    """
    velocity = np.nan_to_num(listings["reviews_per_month"].to_numpy(dtype=float), nan=0.0)
    recent = listings["number_of_reviews_ltm"].to_numpy(dtype=float)
    avail = np.nan_to_num(
        listings["calendar_availability_rate"].to_numpy(dtype=float), nan=0.3
    )

    weight = (0.35 + velocity) * (0.5 + np.log1p(recent)) * (0.25 + avail)
    weight = np.clip(weight, 1e-4, None)
    return weight / weight.sum()


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------


class ExperimentGenerator:
    def __init__(self, listings: pd.DataFrame, config: ExperimentConfig | None = None,
                 seed: int | None = None):
        self.listings = listings.reset_index(drop=True)
        self.cfg = config or EXPERIMENT
        self.rng = np.random.default_rng(seed if seed is not None else self.cfg.seed)

    # ---- randomisation ---------------------------------------------------

    def assign_users(self, n_users: int) -> pd.DataFrame:
        """Randomise each user exactly once.

        Deliberately a plain draw with p=[0.5, 0.5]. No post-hoc balancing, no
        forcing the split to land on exactly 50/50 — the sample ratio mismatch
        check downstream is only meaningful if the split is genuinely random.
        """
        variant = self.rng.choice(
            np.array(["A", "B"]), size=n_users, p=list(self.cfg.allocation)
        )
        users = pd.DataFrame({
            "user_id": np.arange(1, n_users + 1, dtype=np.int64),
            "variant": variant,
        })
        counts = users["variant"].value_counts().to_dict()
        log.info("users randomised", extra={"A": counts.get("A", 0),
                                            "B": counts.get("B", 0)})
        return users

    # ---- sessions --------------------------------------------------------

    def build_sessions(self, users: pd.DataFrame) -> pd.DataFrame:
        cfg = self.cfg
        n_users = len(users)

        # Most visitors have one session; a tail returns two or three times.
        extra = self.rng.poisson(cfg.sessions_per_user - 1.0, size=n_users)
        session_counts = 1 + np.minimum(extra, 4)

        user_ids = np.repeat(users["user_id"].to_numpy(), session_counts)
        variants = np.repeat(users["variant"].to_numpy(), session_counts)
        n_sessions = len(user_ids)

        # Timing: weekday traffic shape x diurnal shape.
        start = pd.Timestamp(cfg.start_date, tz="UTC")
        weekdays = np.array([(start + pd.Timedelta(days=int(d))).weekday()
                             for d in range(cfg.n_days)])
        day_weights = WEEKDAY_TRAFFIC[weekdays]
        # Mild organic growth across the run.
        day_weights = day_weights * np.linspace(0.94, 1.08, cfg.n_days)
        day_weights = day_weights / day_weights.sum()

        day_index = self.rng.choice(cfg.n_days, size=n_sessions, p=day_weights)
        hour = self.rng.choice(24, size=n_sessions, p=HOUR_WEIGHTS / HOUR_WEIGHTS.sum())
        minute = self.rng.integers(0, 60, size=n_sessions)
        second = self.rng.integers(0, 60, size=n_sessions)

        started_at = (
            start
            + pd.to_timedelta(day_index, unit="D")
            + pd.to_timedelta(hour, unit="h")
            + pd.to_timedelta(minute, unit="m")
            + pd.to_timedelta(second, unit="s")
        )

        listing_idx = self.rng.choice(
            len(self.listings), size=n_sessions, p=self._exposure
        )

        device = self.rng.choice(np.array(DEVICES), size=n_sessions, p=list(DEVICE_WEIGHTS))
        traffic = self.rng.choice(
            np.array(TRAFFIC_SOURCES), size=n_sessions, p=list(TRAFFIC_WEIGHTS)
        )

        sessions = pd.DataFrame({
            "user_id": user_ids,
            "variant": variants,
            "listing_idx": listing_idx,
            "session_started_at": started_at,
            "day_index": day_index,
            "device": device,
            "traffic_source": traffic,
        })

        sessions = sessions.sort_values(
            ["user_id", "session_started_at"], kind="mergesort"
        ).reset_index(drop=True)
        sessions["is_returning_user"] = sessions.groupby("user_id").cumcount() > 0
        sessions.insert(0, "session_id", np.arange(1, len(sessions) + 1, dtype=np.int64))
        sessions["listing_id"] = (
            self.listings["listing_id"].to_numpy()[sessions["listing_idx"].to_numpy()]
        )
        sessions["weekday"] = sessions["session_started_at"].dt.weekday
        return sessions

    # ---- funnel ----------------------------------------------------------

    def simulate_funnel(self, sessions: pd.DataFrame) -> pd.DataFrame:
        cfg = self.cfg
        n = len(sessions)
        idx = sessions["listing_idx"].to_numpy()

        appeal = self._appeal_centred[idx]
        device = sessions["device"].to_numpy()
        traffic_effect = _centre(
            sessions["traffic_source"].map(TRAFFIC_EFFECT).fillna(0.0).to_numpy(dtype=float)
        )
        returning = np.where(sessions["is_returning_user"].to_numpy(dtype=bool), 0.19, -0.03)
        weekday_effect = WEEKDAY_CONVERSION[sessions["weekday"].to_numpy()]

        dev_cta = np.array([DEVICE_EFFECT[d]["cta"] for d in device])
        dev_checkout = np.array([DEVICE_EFFECT[d]["checkout"] for d in device])
        dev_booking = np.array([DEVICE_EFFECT[d]["booking"] for d in device])

        is_treatment = (sessions["variant"].to_numpy() == "B").astype(float)
        novelty = self._novelty(sessions["day_index"].to_numpy())

        lift_cta = cfg.treatment_logit_cta * novelty * is_treatment
        lift_checkout = cfg.treatment_logit_checkout * novelty * is_treatment
        lift_booking = cfg.treatment_logit_booking * novelty * is_treatment

        # Unmodelled per-session heterogeneity (intent, dates, party size...).
        noise = self.rng.normal(0.0, 0.28, size=n)

        p_cta = expit(
            logit(cfg.base_cta_click)
            + 0.95 * appeal + _centre(dev_cta) + 0.85 * traffic_effect
            + returning + weekday_effect + noise + lift_cta
        )
        p_checkout = expit(
            logit(cfg.base_checkout_given_cta)
            + 0.60 * appeal + _centre(dev_checkout) + 0.45 * traffic_effect
            + 0.5 * weekday_effect + 0.6 * noise + lift_checkout
        )
        p_booking = expit(
            logit(cfg.base_booking_given_checkout)
            + 0.50 * appeal + _centre(dev_booking) + 0.30 * traffic_effect
            + 0.4 * noise + lift_booking
        )

        clicked = self.rng.random(n) < p_cta
        checked_out = clicked & (self.rng.random(n) < p_checkout)
        booked = checked_out & (self.rng.random(n) < p_booking)

        out = sessions.copy()
        out["clicked_cta"] = clicked
        out["started_checkout"] = checked_out
        out["converted"] = booked
        return out

    def _novelty(self, day_index: np.ndarray) -> np.ndarray:
        """Treatment effects are usually inflated on day one, then settle."""
        cfg = self.cfg
        decay = 0.5 ** (day_index / cfg.novelty_halflife_days)
        return 1.0 + (cfg.novelty_multiplier - 1.0) * decay

    # ---- events ----------------------------------------------------------

    def build_events(self, sessions: pd.DataFrame) -> pd.DataFrame:
        rng = self.rng
        frames = []
        base = sessions["session_started_at"]

        def add(mask: pd.Series | np.ndarray, event_type: str, offset: pd.Series,
                seq: int) -> pd.Series:
            subset = sessions.loc[mask, "session_id"]
            times = (base[mask] + offset[mask]).rename("event_timestamp")
            frames.append(pd.DataFrame({
                "session_id": subset.to_numpy(),
                "event_type": event_type,
                "event_timestamp": times.to_numpy(),
                "sequence_no": seq,
            }))
            return times

        all_mask = np.ones(len(sessions), dtype=bool)
        zero = pd.Series(pd.to_timedelta(np.zeros(len(sessions)), unit="s"),
                         index=sessions.index)
        add(all_mask, "listing_view", zero, 1)

        # Time spent reading the listing before tapping the CTA.
        t_cta = pd.Series(
            pd.to_timedelta(np.round(rng.gamma(2.2, 26.0, len(sessions))), unit="s"),
            index=sessions.index,
        )
        clicked = sessions["clicked_cta"].to_numpy()
        add(clicked, "cta_click", t_cta, 2)

        t_checkout = t_cta + pd.Series(
            pd.to_timedelta(np.round(rng.gamma(2.0, 18.0, len(sessions))), unit="s"),
            index=sessions.index,
        )
        checked = sessions["started_checkout"].to_numpy()
        add(checked, "checkout_started", t_checkout, 3)

        t_booking = t_checkout + pd.Series(
            pd.to_timedelta(np.round(rng.gamma(2.6, 34.0, len(sessions))), unit="s"),
            index=sessions.index,
        )
        booked = sessions["converted"].to_numpy()
        add(booked, "booking_completed", t_booking, 4)

        # Session exit always happens last, a little after the deepest step.
        deepest = pd.Series(np.zeros(len(sessions)), index=sessions.index, dtype="float64")
        deepest = deepest.where(~clicked, t_cta.dt.total_seconds())
        deepest = deepest.where(~checked, t_checkout.dt.total_seconds())
        deepest = deepest.where(~booked, t_booking.dt.total_seconds())
        tail = np.round(rng.gamma(1.6, 22.0, len(sessions)))
        t_exit = pd.Series(pd.to_timedelta(deepest.to_numpy() + tail, unit="s"),
                           index=sessions.index)
        add(all_mask, "session_exit", t_exit, 5)

        events = pd.concat(frames, ignore_index=True)
        events = events.sort_values(["session_id", "sequence_no"], kind="mergesort")
        return events.reset_index(drop=True)

    # ---- bookings --------------------------------------------------------

    def build_bookings(self, sessions: pd.DataFrame) -> pd.DataFrame:
        cfg = self.cfg
        rng = self.rng
        booked = sessions[sessions["converted"]].reset_index(drop=True)
        if booked.empty:
            return pd.DataFrame(columns=[
                "booking_id", "session_id", "listing_id", "booking_value", "nights",
                "guests", "checkin_date", "created_at", "is_cancelled", "cancelled_at",
            ])

        idx = booked["listing_idx"].to_numpy()
        listings = self.listings

        min_nights = np.clip(
            np.nan_to_num(listings["calendar_min_nights"].to_numpy(dtype=float)[idx], nan=1.0),
            1, 30,
        )
        nightly = np.nan_to_num(
            listings["calendar_avg_price"].to_numpy(dtype=float)[idx], nan=0.0
        )
        fallback = listings["price"].to_numpy(dtype=float)[idx]
        nightly = np.where(nightly <= 0, fallback, nightly)
        capacity = listings["accommodates"].to_numpy(dtype=float)[idx]

        raw_nights = 1.0 + rng.gamma(2.0, 1.7, size=len(booked))
        # The treatment shows the all-in total up front, which nudges people to
        # trim a night off. A small, honest negative side effect on stay length.
        treatment_mask = booked["variant"].to_numpy() == "B"
        raw_nights = np.where(
            treatment_mask, raw_nights * cfg.treatment_nights_multiplier, raw_nights
        )
        nights = np.clip(np.ceil(raw_nights), min_nights, 21).astype(int)

        guests = np.clip(1 + rng.poisson(0.85, size=len(booked)), 1, capacity).astype(int)

        accommodation = nights * nightly
        cleaning_fee = np.round(np.clip(0.42 * nightly, 12.0, 180.0), 2)
        service_fee = 0.141 * (accommodation + cleaning_fee)
        booking_value = np.round(accommodation + cleaning_fee + service_fee, 2)

        created_at = pd.to_datetime(booked["session_started_at"]) + pd.to_timedelta(
            np.round(rng.gamma(3.0, 40.0, size=len(booked))), unit="s"
        )
        lead_days = np.clip(np.round(rng.gamma(2.2, 18.0, size=len(booked))), 2, 200)
        checkin_date = (created_at + pd.to_timedelta(lead_days, unit="D")).dt.date

        # Guardrail: cancellations. Showing the true total earlier should, if
        # anything, reduce post-booking regret.
        cancel_logit = (
            logit(cfg.base_cancellation_rate)
            + cfg.treatment_logit_cancellation * treatment_mask
            + np.where(booked["device"].to_numpy() == "mobile", 0.14, -0.06)
            + 0.22 * (lead_days > 60)
            + rng.normal(0.0, 0.25, size=len(booked))
        )
        is_cancelled = rng.random(len(booked)) < expit(cancel_logit)
        cancelled_at = pd.Series(pd.NaT, index=booked.index, dtype="datetime64[ns, UTC]")
        cancel_delay = pd.to_timedelta(
            np.round(rng.gamma(1.5, 26.0, size=len(booked))), unit="h"
        )
        cancelled_at = cancelled_at.mask(is_cancelled, created_at + cancel_delay)

        return pd.DataFrame({
            "booking_id": np.arange(1, len(booked) + 1, dtype=np.int64),
            "session_id": booked["session_id"].to_numpy(),
            "listing_id": booked["listing_id"].to_numpy(),
            "booking_value": booking_value,
            "nights": nights,
            "guests": guests,
            "checkin_date": checkin_date,
            "created_at": created_at,
            "is_cancelled": is_cancelled,
            "cancelled_at": cancelled_at,
        })

    # ---- orchestration ---------------------------------------------------

    def run(self) -> dict[str, pd.DataFrame]:
        self._appeal_centred = _centre(listing_appeal(self.listings))
        self._exposure = exposure_weights(self.listings)

        n_users = int(round(self.cfg.n_sessions / self.cfg.sessions_per_user))
        users = self.assign_users(n_users)

        sessions = self.build_sessions(users)
        sessions = self.simulate_funnel(sessions)
        events = self.build_events(sessions)
        bookings = self.build_bookings(sessions)

        assigned_at = (
            sessions.groupby("user_id")["session_started_at"].min().rename("assigned_at")
        )
        users = users.merge(assigned_at, on="user_id", how="left")
        users["assigned_at"] = users["assigned_at"].fillna(
            pd.Timestamp(self.cfg.start_date, tz="UTC")
        )

        log.info(
            "experiment generated",
            extra={
                "users": len(users),
                "sessions": len(sessions),
                "events": len(events),
                "bookings": len(bookings),
                "session_conversion": round(float(sessions["converted"].mean()), 4),
            },
        )
        return {
            "users": users,
            "sessions": sessions,
            "events": events,
            "bookings": bookings,
        }


def generate(listings: pd.DataFrame | None = None,
             config: ExperimentConfig | None = None,
             seed: int | None = None) -> dict[str, pd.DataFrame]:
    if listings is None:
        path = PROCESSED_DIR / "listings.parquet"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. Run `python -m analytics.etl_listings` first."
            )
        listings = pd.read_parquet(path)
    return ExperimentGenerator(listings, config=config, seed=seed).run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the simulated experiment")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--sessions", type=int, default=None)
    args = parser.parse_args()

    cfg = EXPERIMENT
    if args.sessions:
        cfg = ExperimentConfig(n_sessions=args.sessions)

    data = generate(config=cfg, seed=args.seed)
    summary = (
        data["sessions"].groupby("variant")
        .agg(sessions=("session_id", "size"), conversions=("converted", "sum"))
    )
    summary["rate"] = (summary["conversions"] / summary["sessions"]).round(4)
    print(summary.to_string())


if __name__ == "__main__":
    main()

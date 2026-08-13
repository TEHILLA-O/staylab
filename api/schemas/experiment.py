"""Pydantic response models.

The API contract is defined here rather than by whatever the database happens
to return, so a schema change downstream surfaces as a validation error instead
of quietly reshaping the dashboard.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# --------------------------------------------------------------------------
# Experiment metadata
# --------------------------------------------------------------------------


class ExperimentSummaryCard(Base):
    experiment_id: int
    experiment_key: str
    name: str
    surface: str
    status: Literal["running", "completed", "stopped"]
    primary_metric: str
    randomisation_unit: str
    significance_level: float
    started_at: date
    ended_at: date | None = None
    users: int
    sessions: int
    is_simulated: bool
    data_source: str


class ExperimentDetail(ExperimentSummaryCard):
    hypothesis: str
    control_label: str
    treatment_label: str
    duration_days: int
    first_session_at: str | None = None
    last_session_at: str | None = None


# --------------------------------------------------------------------------
# Aggregates
# --------------------------------------------------------------------------


class VariantSummary(Base):
    variant: Literal["A", "B"]
    variant_label: str
    users: int
    sessions: int
    converted_users: int
    conversions: int
    cta_clicks: int
    checkout_starts: int
    bounces: int
    cancellations: int
    gross_revenue: float
    net_revenue: float
    conversion_rate: float
    session_conversion_rate: float
    cta_click_rate: float
    checkout_start_rate: float
    bounce_rate: float
    checkout_abandon_rate: float | None = None
    cancellation_rate: float | None = None
    average_booking_value: float | None = None
    revenue_per_visitor: float | None = None
    allocation_share: float
    conversion_absolute_uplift: float | None = None
    conversion_relative_uplift: float | None = None


class MetricComparison(Base):
    metric: str
    label: str
    format: Literal["percent", "currency", "number"]
    control_value: float | None = None
    treatment_value: float | None = None
    absolute_change: float | None = None
    relative_change: float | None = None


class Guardrail(Base):
    metric: str
    label: str
    direction: Literal["lower_is_better", "higher_is_better", "neutral"]
    control_value: float | None = None
    treatment_value: float | None = None
    absolute_change: float | None = None
    relative_change: float | None = None
    breached: bool


class TimeseriesPoint(Base):
    session_date: date
    day_number: int
    sessions: int
    control_daily: float | None = None
    treatment_daily: float | None = None
    control_cumulative: float | None = None
    treatment_cumulative: float | None = None
    cumulative_absolute_lift: float | None = None
    cumulative_relative_lift: float | None = None


class SegmentRow(Base):
    segment_value: str
    sessions: int
    users: int
    control_sessions: int | None = None
    treatment_sessions: int | None = None
    control_conversions: int | None = None
    treatment_conversions: int | None = None
    control_rate: float | None = None
    treatment_rate: float | None = None
    absolute_lift: float | None = None
    relative_lift: float | None = None
    control_revenue: float | None = None
    treatment_revenue: float | None = None
    low_sample: bool
    size_rank: int


class SegmentResponse(Base):
    segment_type: Literal["device", "traffic_source", "neighbourhood", "room_type"]
    rows: list[SegmentRow]


class FunnelStep(Base):
    step_order: int
    step: str
    control_sessions: int
    treatment_sessions: int
    control_step_rate: float | None = None
    treatment_step_rate: float | None = None
    control_cumulative_rate: float | None = None
    treatment_cumulative_rate: float | None = None
    step_relative_lift: float | None = None


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------


class ProportionTestOut(Base):
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


class MeansTestOut(Base):
    control_mean: float
    treatment_mean: float
    absolute_uplift: float
    relative_uplift: float
    confidence_interval: tuple[float, float]
    t_statistic: float
    p_value: float
    statistically_significant: bool


class SampleRatioOut(Base):
    control_units: int
    treatment_units: int
    expected_ratio: float
    observed_ratio: float
    chi_square: float
    p_value: float
    mismatch_detected: bool


class MdeOut(Base):
    baseline_rate: float
    n_per_variant: int
    alpha: float
    power: float
    mde_absolute: float
    mde_relative: float


class PlannedSampleOut(Base):
    baseline_rate: float
    mde_relative: float
    mde_absolute: float
    target_rate: float
    alpha: float
    power: float
    effect_size: float
    required_per_variant: int
    required_total: int


class StatisticsBundle(Base):
    primary: ProportionTestOut
    secondary: dict[str, ProportionTestOut]
    revenue_per_visitor: MeansTestOut
    sample_ratio: SampleRatioOut
    minimum_detectable_effect: MdeOut
    planned_sample_size: PlannedSampleOut


class DecisionOut(Base):
    verdict: Literal["significant", "inconclusive", "negative"]
    decision: Literal["ship", "iterate", "do_not_ship", "keep_running"]
    headline: str
    rationale: list[str]
    guardrails_ok: bool


class ProjectedImpact(Base):
    annual_visitors: int
    revenue_per_visitor_delta: float | None = None
    annualised_gross_booking_delta: float | None = None
    platform_take_rate: float
    annualised_revenue_delta: float | None = None
    basis: str


class ValidationCheck(Base):
    name: str
    passed: bool
    detail: str
    severity: Literal["error", "warning"]


class ExperimentAnalysis(Base):
    experiment: ExperimentDetail
    summary: list[VariantSummary]
    secondary_metrics: list[MetricComparison]
    guardrails: list[Guardrail]
    statistics: StatisticsBundle
    decision: DecisionOut
    projected_impact: ProjectedImpact
    validation: list[ValidationCheck] = Field(default_factory=list)


class MarketplaceOverview(Base):
    listings: int
    neighbourhoods: int
    avg_price: float
    median_price: float
    avg_review_score: float | None = None
    superhost_share: float
    instant_bookable_share: float
    listings_with_traffic: int
    avg_sessions_per_listing: float
    max_sessions_per_listing: int


class SqlQuery(Base):
    name: str
    title: str
    description: str
    sql: str


class HealthResponse(Base):
    status: Literal["ok", "degraded"]
    database: bool
    version: str

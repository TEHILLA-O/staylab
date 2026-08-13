export type Verdict = "significant" | "inconclusive" | "negative";
export type Decision = "ship" | "iterate" | "do_not_ship" | "keep_running";
export type SegmentType = "device" | "traffic_source" | "neighbourhood" | "room_type";

export interface ExperimentDetail {
  experiment_id: number;
  experiment_key: string;
  name: string;
  surface: string;
  status: "running" | "completed" | "stopped";
  primary_metric: string;
  randomisation_unit: string;
  significance_level: number;
  started_at: string;
  ended_at: string | null;
  users: number;
  sessions: number;
  is_simulated: boolean;
  data_source: string;
  hypothesis: string;
  control_label: string;
  treatment_label: string;
  duration_days: number;
  first_session_at: string | null;
  last_session_at: string | null;
}

export interface VariantSummary {
  variant: "A" | "B";
  variant_label: string;
  users: number;
  sessions: number;
  converted_users: number;
  conversions: number;
  conversion_rate: number;
  allocation_share: number;
  conversion_absolute_uplift: number | null;
  conversion_relative_uplift: number | null;
}

export interface MetricComparison {
  metric: string;
  label: string;
  format: "percent" | "currency" | "number";
  control_value: number | null;
  treatment_value: number | null;
  absolute_change: number | null;
  relative_change: number | null;
}

export interface Guardrail {
  metric: string;
  label: string;
  direction: "lower_is_better" | "higher_is_better" | "neutral";
  control_value: number | null;
  treatment_value: number | null;
  absolute_change: number | null;
  relative_change: number | null;
  breached: boolean;
}

export interface TimeseriesPoint {
  session_date: string;
  day_number: number;
  sessions: number;
  control_daily: number | null;
  treatment_daily: number | null;
  control_cumulative: number | null;
  treatment_cumulative: number | null;
  cumulative_absolute_lift: number | null;
  cumulative_relative_lift: number | null;
}

export interface SegmentRow {
  segment_value: string;
  sessions: number;
  users: number;
  control_sessions: number | null;
  treatment_sessions: number | null;
  control_rate: number | null;
  treatment_rate: number | null;
  absolute_lift: number | null;
  relative_lift: number | null;
  low_sample: boolean;
  size_rank: number;
}

export interface FunnelStep {
  step_order: number;
  step: string;
  control_sessions: number;
  treatment_sessions: number;
  control_step_rate: number | null;
  treatment_step_rate: number | null;
  control_cumulative_rate: number | null;
  treatment_cumulative_rate: number | null;
  step_relative_lift: number | null;
}

export interface ProportionTest {
  control_visitors: number;
  treatment_visitors: number;
  control_conversions: number;
  treatment_conversions: number;
  control_rate: number;
  treatment_rate: number;
  control_rate_ci: [number, number];
  treatment_rate_ci: [number, number];
  absolute_uplift: number;
  relative_uplift: number;
  confidence_interval: [number, number];
  relative_confidence_interval: [number, number];
  z_score: number;
  p_value: number;
  standard_error: number;
  confidence_level: number;
  significance_level: number;
  statistically_significant: boolean;
  observed_power: number;
}

export interface SampleRatio {
  control_units: number;
  treatment_units: number;
  expected_ratio: number;
  observed_ratio: number;
  chi_square: number;
  p_value: number;
  mismatch_detected: boolean;
}

export interface ExperimentAnalysis {
  experiment: ExperimentDetail;
  summary: VariantSummary[];
  secondary_metrics: MetricComparison[];
  guardrails: Guardrail[];
  statistics: {
    primary: ProportionTest;
    sample_ratio: SampleRatio;
    minimum_detectable_effect: {
      mde_absolute: number;
      mde_relative: number;
      n_per_variant: number;
    };
  };
  decision: {
    verdict: Verdict;
    decision: Decision;
    headline: string;
    rationale: string[];
    guardrails_ok: boolean;
  };
  projected_impact: {
    annual_visitors: number;
    annualised_gross_booking_delta: number | null;
    platform_take_rate: number;
    annualised_revenue_delta: number | null;
    basis: string;
  };
  validation: Array<{
    name: string;
    passed: boolean;
    detail: string;
    severity: "error" | "warning";
  }>;
}

export interface SqlQuery {
  name: string;
  title: string;
  description: string;
  sql: string;
}

export interface MarketplaceOverview {
  listings: number;
  neighbourhoods: number;
  avg_price: number;
  median_price: number;
  avg_review_score: number | null;
  superhost_share: number;
  instant_bookable_share: number;
  listings_with_traffic: number;
}

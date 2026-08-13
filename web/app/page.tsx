"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AnalysisPanel } from "@/components/AnalysisPanel";
import { ConversionChart } from "@/components/ConversionChart";
import { DecisionBlock } from "@/components/DecisionBlock";
import { EffectPanel } from "@/components/EffectPanel";
import { SegmentTable } from "@/components/SegmentTable";
import { SqlExplorer } from "@/components/SqlExplorer";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { VariantHero } from "@/components/VariantHero";
import { ApiError, api } from "@/lib/api";
import { compact, formatDay } from "@/lib/format";
import type {
  ExperimentAnalysis,
  FunnelStep,
  MarketplaceOverview,
  SegmentRow,
  SegmentType,
  TimeseriesPoint,
} from "@/types/experiment";

type Tab = "experiment" | "analysis" | "sql";

export default function HomePage() {
  const [analysis, setAnalysis] = useState<ExperimentAnalysis | null>(null);
  const [series, setSeries] = useState<TimeseriesPoint[]>([]);
  const [segments, setSegments] = useState<SegmentRow[]>([]);
  const [segmentType, setSegmentType] = useState<SegmentType>("device");
  const [segmentLoading, setSegmentLoading] = useState(false);
  const [funnel, setFunnel] = useState<FunnelStep[]>([]);
  const [marketplace, setMarketplace] = useState<MarketplaceOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("experiment");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [payload, points, segs, steps, market] = await Promise.all([
        api.analysis(),
        api.timeseries(),
        api.segments("device"),
        api.funnel(),
        api.marketplace(),
      ]);
      setAnalysis(payload);
      setSeries(points);
      setSegments(segs.rows);
      setFunnel(steps);
      setMarketplace(market);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unexpected error");
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!analysis) return;
    setSegmentLoading(true);
    api
      .segments(segmentType)
      .then((res) => setSegments(res.rows))
      .catch(() => undefined)
      .finally(() => setSegmentLoading(false));
  }, [segmentType, analysis]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!analysis) return <EmptyState />;

  const { experiment, statistics, decision } = analysis;
  const today = formatDay(experiment.last_session_at ?? new Date().toISOString());

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-[880px] px-6 pb-24 pt-10 sm:px-10">
        <header className="flex items-baseline justify-between">
          <div>
            <p className="font-serif text-[28px] leading-none text-ink">StayLab</p>
            <p className="mt-2 text-xs tracking-label text-mute uppercase">Experimentation</p>
          </div>
          <p className="text-sm text-mute">{today}</p>
        </header>

        <p className="label mt-16">
          {experiment.surface} · {experiment.experiment_key}
        </p>
        <h1 className="mt-3 font-serif text-4xl leading-tight text-ink sm:text-[44px]">
          {experiment.name}
        </h1>
        <p className="mt-5 max-w-xl text-[16px] leading-relaxed text-mute">
          {experiment.hypothesis}
        </p>
        <p className="mt-6 text-sm text-mute">
          <span className="text-ink">{experiment.status.toUpperCase()}</span>
          <span className="mx-2 text-line">·</span>
          {compact(experiment.sessions)} sessions
          <span className="mx-2 text-line">·</span>
          {experiment.duration_days} days
          <span className="mx-2 text-line">·</span>
          {compact(experiment.users)} users
        </p>
        <p className="mt-4 max-w-xl text-xs leading-relaxed text-mute">
          Listing attributes are real Inside Airbnb London data (19 June 2026). The event
          stream, assignments and bookings are simulated. Metrics are computed from stored
          data, not hard-coded.
        </p>

        <nav className="mt-10 flex gap-6 border-b border-line text-sm">
          {(
            [
              ["experiment", "Experiment"],
              ["analysis", "Analysis"],
              ["sql", "SQL"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`-mb-px border-b py-3 ${
                tab === id ? "border-ink text-ink" : "border-transparent text-mute"
              }`}
            >
              {label}
            </button>
          ))}
          <Link href="/methodology" className="-mb-px border-b border-transparent py-3 text-mute">
            Methodology
          </Link>
        </nav>

        {tab === "experiment" ? (
          <div className="mt-14 space-y-16">
            <VariantHero test={statistics.primary} />
            <div className="hairline" />
            <EffectPanel
              test={statistics.primary}
              verdict={decision.verdict}
              headline={decision.headline}
              decision={decision.decision}
            />
            <div className="hairline" />
            <ConversionChart series={series} />
            <div className="hairline" />
            <SegmentTable
              rows={segments}
              segmentType={segmentType}
              onChange={setSegmentType}
              loading={segmentLoading}
            />
            <div className="hairline" />
            <DecisionBlock
              analysis={analysis}
              onViewAnalysis={() => setTab("analysis")}
            />
          </div>
        ) : null}

        {tab === "analysis" ? (
          <div className="mt-14">
            <AnalysisPanel
              analysis={analysis}
              funnel={funnel}
              marketplace={marketplace}
            />
          </div>
        ) : null}

        {tab === "sql" ? (
          <div className="mt-14">
            <SqlExplorer />
          </div>
        ) : null}

        <footer className="mt-24 border-t border-line pt-6 text-xs leading-relaxed text-mute">
          StayLab · EXP-024 · Randomisation unit is the user · Inside Airbnb London snapshot
          19 June 2026 · Event data is simulated
        </footer>
      </div>
    </main>
  );
}

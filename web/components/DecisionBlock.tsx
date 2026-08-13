import { decisionLabel, gbp } from "@/lib/format";
import type { ExperimentAnalysis } from "@/types/experiment";

export function DecisionBlock({
  analysis,
  onViewAnalysis,
}: {
  analysis: ExperimentAnalysis;
  onViewAnalysis: () => void;
}) {
  const { decision, projected_impact: impact } = analysis;
  const revenue = impact.annualised_revenue_delta;

  return (
    <section>
      <p className="label">Decision</p>
      <h2 className="mt-4 max-w-xl font-serif text-3xl leading-snug text-ink">
        {decision.headline}
      </h2>
      <ul className="mt-6 max-w-xl space-y-3 text-[15px] leading-relaxed text-mute">
        {decision.rationale.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>

      <div className="mt-10 flex flex-wrap items-end justify-between gap-6 border-t border-line pt-8">
        <div>
          <p className="label">Potential annualised impact</p>
          <p className="num mt-2 font-serif text-3xl text-ink">
            {revenue == null ? "—" : `${revenue >= 0 ? "+" : ""}${gbp(revenue)}`}
          </p>
          <p className="mt-2 max-w-md text-xs leading-relaxed text-mute">
            Platform take of {(impact.platform_take_rate * 100).toFixed(0)}% on incremental
            bookings. A projection, not a measured outcome.
          </p>
        </div>
        <div className="flex items-center gap-4">
          <p className="label">{decisionLabel(decision.decision)}</p>
          <button
            type="button"
            onClick={onViewAnalysis}
            className="border border-ink px-4 py-2 text-sm text-ink hover:bg-ink hover:text-canvas"
          >
            View analysis
          </button>
        </div>
      </div>
    </section>
  );
}

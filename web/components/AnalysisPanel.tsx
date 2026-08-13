import { compact, pct, signedPct, titleCase } from "@/lib/format";
import type { ExperimentAnalysis, FunnelStep, MarketplaceOverview } from "@/types/experiment";

function metricValue(format: string, value: number | null) {
  if (value == null) return "—";
  if (format === "percent") return pct(value);
  if (format === "currency") {
    return new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency: "GBP",
      maximumFractionDigits: 2,
    }).format(value);
  }
  return compact(value);
}

export function AnalysisPanel({
  analysis,
  funnel,
  marketplace,
}: {
  analysis: ExperimentAnalysis;
  funnel: FunnelStep[];
  marketplace: MarketplaceOverview | null;
}) {
  return (
    <div className="space-y-16">
      <section>
        <h2 className="font-serif text-2xl text-ink">Secondary metrics</h2>
        <table className="mt-6 w-full text-sm">
          <thead>
            <tr className="label border-b border-line">
              <th className="py-3 text-left font-normal">Metric</th>
              <th className="py-3 text-right font-normal">Control</th>
              <th className="py-3 text-right font-normal">Treatment</th>
              <th className="py-3 text-right font-normal">Change</th>
            </tr>
          </thead>
          <tbody>
            {analysis.secondary_metrics.map((row) => (
              <tr key={row.metric} className="border-b border-line/70">
                <td className="py-3">{row.label}</td>
                <td className="num py-3 text-right">
                  {metricValue(row.format, row.control_value)}
                </td>
                <td className="num py-3 text-right">
                  {metricValue(row.format, row.treatment_value)}
                </td>
                <td
                  className={`num py-3 text-right ${
                    (row.relative_change ?? 0) >= 0 ? "text-up" : "text-down"
                  }`}
                >
                  {signedPct(row.relative_change)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2 className="font-serif text-2xl text-ink">Funnel</h2>
        <p className="mt-1 text-sm text-mute">
          Where in the flow the treatment moved the numbers.
        </p>
        <table className="mt-6 w-full text-sm">
          <thead>
            <tr className="label border-b border-line">
              <th className="py-3 text-left font-normal">Step</th>
              <th className="py-3 text-right font-normal">Control</th>
              <th className="py-3 text-right font-normal">Treatment</th>
              <th className="py-3 text-right font-normal">Step lift</th>
            </tr>
          </thead>
          <tbody>
            {funnel.map((step) => (
              <tr key={step.step} className="border-b border-line/70">
                <td className="py-3">{titleCase(step.step)}</td>
                <td className="num py-3 text-right">{pct(step.control_step_rate)}</td>
                <td className="num py-3 text-right">{pct(step.treatment_step_rate)}</td>
                <td
                  className={`num py-3 text-right ${
                    (step.step_relative_lift ?? 0) >= 0 ? "text-up" : "text-down"
                  }`}
                >
                  {signedPct(step.step_relative_lift)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2 className="font-serif text-2xl text-ink">Guardrails</h2>
        <ul className="mt-6 space-y-4">
          {analysis.guardrails.map((g) => (
            <li key={g.metric} className="flex items-baseline justify-between gap-6 text-sm">
              <span>
                {g.label}
                {g.breached ? <span className="ml-2 text-down">breach</span> : null}
              </span>
              <span className="num text-mute">
                {g.metric.includes("rate")
                  ? `${pct(g.control_value)} → ${pct(g.treatment_value)}`
                  : `${compact(g.control_value)} → ${compact(g.treatment_value)}`}
                <span className="ml-3">{signedPct(g.relative_change)}</span>
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="font-serif text-2xl text-ink">Validation</h2>
        <ul className="mt-6 space-y-4">
          {analysis.validation.map((check) => (
            <li key={check.name} className="text-sm">
              <span className={check.passed ? "text-up" : "text-down"}>
                {check.passed ? "Pass" : check.severity === "warning" ? "Warn" : "Fail"}
              </span>
              <span className="ml-3 text-ink">{check.name}</span>
              <p className="mt-1 text-mute">{check.detail}</p>
            </li>
          ))}
        </ul>
      </section>

      {marketplace ? (
        <section>
          <h2 className="font-serif text-2xl text-ink">Marketplace context</h2>
          <p className="mt-1 text-sm text-mute">
            Real Inside Airbnb London listings the experiment sampled from. Not simulated.
          </p>
          <dl className="mt-6 grid grid-cols-2 gap-x-8 gap-y-5 text-sm sm:grid-cols-3">
            <div>
              <dt className="label">Listings</dt>
              <dd className="num mt-1 text-ink">{compact(marketplace.listings)}</dd>
            </div>
            <div>
              <dt className="label">Neighbourhoods</dt>
              <dd className="num mt-1 text-ink">{compact(marketplace.neighbourhoods)}</dd>
            </div>
            <div>
              <dt className="label">Median night</dt>
              <dd className="num mt-1 text-ink">
                {new Intl.NumberFormat("en-GB", {
                  style: "currency",
                  currency: "GBP",
                  maximumFractionDigits: 0,
                }).format(marketplace.median_price)}
              </dd>
            </div>
            <div>
              <dt className="label">Superhost share</dt>
              <dd className="num mt-1 text-ink">{pct(marketplace.superhost_share)}</dd>
            </div>
            <div>
              <dt className="label">Instant bookable</dt>
              <dd className="num mt-1 text-ink">{pct(marketplace.instant_bookable_share)}</dd>
            </div>
            <div>
              <dt className="label">Listings with traffic</dt>
              <dd className="num mt-1 text-ink">{compact(marketplace.listings_with_traffic)}</dd>
            </div>
          </dl>
        </section>
      ) : null}
    </div>
  );
}

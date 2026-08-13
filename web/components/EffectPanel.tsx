import { pValue, pp } from "@/lib/format";
import type { Decision, ProportionTest, Verdict } from "@/types/experiment";

const VERDICT: Record<Verdict, string> = {
  significant: "Significant",
  inconclusive: "Inconclusive",
  negative: "Negative",
};

function trackRange(lo: number, hi: number, observed: number) {
  const span = Math.max(hi - lo, Math.abs(observed) * 2, 0.004);
  const pad = span * 0.28;
  const min = Math.min(lo, 0, observed) - pad;
  const max = Math.max(hi, 0, observed) + pad;
  const pct = (value: number) => ((value - min) / (max - min)) * 100;
  return { pct };
}

export function EffectPanel({
  test,
  verdict,
  headline,
}: {
  test: ProportionTest;
  verdict: Verdict;
  headline: string;
  decision: Decision;
}) {
  const [lo, hi] = test.confidence_interval;
  const { pct } = trackRange(lo, hi, test.absolute_uplift);
  const color =
    verdict === "negative" ? "bg-down" : verdict === "significant" ? "bg-accent" : "bg-warm";

  return (
    <section className="text-center">
      <p className="num font-serif text-5xl tracking-tight text-ink">{pp(test.absolute_uplift)}</p>
      <p className="label mt-3">Observed effect</p>

      <div className="relative mx-auto mt-10 h-10 max-w-[420px]">
        <div className="absolute left-0 right-0 top-1/2 h-px -translate-y-1/2 bg-line" />
        <div
          className="absolute top-1/2 h-px -translate-y-1/2 bg-ink/50"
          style={{
            left: `${Math.min(pct(lo), pct(hi))}%`,
            width: `${Math.abs(pct(hi) - pct(lo))}%`,
          }}
        />
        <div
          className="absolute top-1/2 h-3 w-px -translate-y-1/2 bg-ink/40"
          style={{ left: `${pct(0)}%` }}
        />
        <div
          className={`absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ${color}`}
          style={{ left: `${pct(test.absolute_uplift)}%` }}
        />
      </div>
      <p className="mt-3 text-xs text-mute">95% confidence</p>
      <p className="label mt-8">
        [{pp(lo)}, {pp(hi)}]
      </p>
      <p className="num mt-6 text-sm text-mute">p = {pValue(test.p_value)}</p>
      <p className="mt-8 font-serif text-3xl text-ink">{VERDICT[verdict]}</p>
      <p className="mx-auto mt-3 max-w-sm text-[15px] leading-relaxed text-mute">{headline}</p>
    </section>
  );
}

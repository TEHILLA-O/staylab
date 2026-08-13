import { compact, pct, signedPct } from "@/lib/format";
import type { ProportionTest } from "@/types/experiment";

export function VariantHero({ test }: { test: ProportionTest }) {
  return (
    <section className="grid grid-cols-1 gap-12 sm:grid-cols-2 sm:gap-16">
      <div>
        <p className="label">Control A</p>
        <p className="num mt-4 font-serif text-[56px] leading-none tracking-tight text-ink sm:text-[64px]">
          {pct(test.control_rate)}
        </p>
        <p className="mt-3 text-sm text-mute">
          Conversion
          <span className="mx-2 text-line">·</span>
          {compact(test.control_conversions)} / {compact(test.control_visitors)} users
        </p>
      </div>
      <div>
        <p className="label">Treatment B</p>
        <p className="num mt-4 font-serif text-[56px] leading-none tracking-tight text-ink sm:text-[64px]">
          {pct(test.treatment_rate)}
        </p>
        <p className="mt-3 text-sm text-mute">
          Conversion
          <span className="mx-2 text-line">·</span>
          {compact(test.treatment_conversions)} / {compact(test.treatment_visitors)} users
        </p>
        <p
          className={`mt-4 text-sm ${test.relative_uplift >= 0 ? "text-up" : "text-down"}`}
        >
          ↑ {signedPct(test.relative_uplift)} relative uplift
        </p>
      </div>
    </section>
  );
}

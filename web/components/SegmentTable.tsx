"use client";

import { compact, pct, signedPct, titleCase } from "@/lib/format";
import type { SegmentRow, SegmentType } from "@/types/experiment";

const TABS: { id: SegmentType; label: string }[] = [
  { id: "device", label: "Device" },
  { id: "traffic_source", label: "Traffic source" },
  { id: "neighbourhood", label: "Neighbourhood" },
];

export function SegmentTable({
  rows,
  segmentType,
  onChange,
  loading,
}: {
  rows: SegmentRow[];
  segmentType: SegmentType;
  onChange: (next: SegmentType) => void;
  loading: boolean;
}) {
  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="font-serif text-2xl text-ink">Performance by segment</h2>
          <p className="mt-1 text-sm text-mute">
            Session-level conversion. Rows under 1,000 sessions per arm are marked.
          </p>
        </div>
        <div className="flex gap-1 border-b border-line">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => onChange(tab.id)}
              className={`px-3 py-2 text-sm ${
                segmentType === tab.id
                  ? "border-b border-ink text-ink"
                  : "text-mute hover:text-ink"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead>
            <tr className="label border-b border-line">
              <th className="py-3 font-normal">Segment</th>
              <th className="py-3 text-right font-normal">Control</th>
              <th className="py-3 text-right font-normal">Treatment</th>
              <th className="py-3 text-right font-normal">Lift</th>
              <th className="py-3 text-right font-normal">Sessions</th>
            </tr>
          </thead>
          <tbody className={loading ? "opacity-50" : ""}>
            {rows.map((row) => {
              const lift = row.relative_lift;
              const liftClass =
                lift == null ? "text-mute" : lift >= 0 ? "text-up" : "text-down";
              return (
                <tr key={row.segment_value} className="border-b border-line/70">
                  <td className="py-3 text-ink">
                    {titleCase(row.segment_value)}
                    {row.low_sample ? (
                      <span className="ml-2 text-xs text-mute">low n</span>
                    ) : null}
                  </td>
                  <td className="num py-3 text-right text-ink">{pct(row.control_rate)}</td>
                  <td className="num py-3 text-right text-ink">{pct(row.treatment_rate)}</td>
                  <td className={`num py-3 text-right ${liftClass}`}>{signedPct(lift)}</td>
                  <td className="num py-3 text-right text-mute">{compact(row.sessions)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

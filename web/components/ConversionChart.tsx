"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatDay, pct } from "@/lib/format";
import type { TimeseriesPoint } from "@/types/experiment";

function tick(value: number) {
  return `${(value * 100).toFixed(0)}%`;
}

export function ConversionChart({ series }: { series: TimeseriesPoint[] }) {
  if (!series.length) {
    return <p className="text-sm text-mute">No daily observations yet.</p>;
  }

  return (
    <section>
      <div className="flex items-end justify-between gap-6">
        <div>
          <h2 className="font-serif text-2xl text-ink">Conversion</h2>
          <p className="mt-1 text-sm text-mute">Cumulative booking rate by day of the experiment.</p>
        </div>
        <div className="flex gap-5 text-xs text-mute">
          <span className="flex items-center gap-2">
            <i className="h-px w-5 bg-ink/50" /> A
          </span>
          <span className="flex items-center gap-2">
            <i className="h-px w-5 bg-accent" /> B
          </span>
        </div>
      </div>
      <div className="mt-8 h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="#E4E4DF" />
            <XAxis
              dataKey="session_date"
              tickFormatter={formatDay}
              tick={{ fill: "#70706C", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              minTickGap={28}
            />
            <YAxis
              tickFormatter={tick}
              tick={{ fill: "#70706C", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={42}
              domain={["auto", "auto"]}
            />
            <Tooltip
              contentStyle={{
                border: "1px solid #E4E4DF",
                borderRadius: 0,
                boxShadow: "none",
                background: "#FFFFFF",
                fontSize: 12,
              }}
              formatter={(value, name) => [
                pct(Number(value)),
                name === "control_cumulative" ? "Control A" : "Treatment B",
              ]}
              labelFormatter={(label) => formatDay(String(label))}
            />
            <Line
              type="monotone"
              dataKey="control_cumulative"
              stroke="#181818"
              strokeWidth={1.4}
              strokeOpacity={0.55}
              dot={false}
              activeDot={{ r: 3, fill: "#181818" }}
            />
            <Line
              type="monotone"
              dataKey="treatment_cumulative"
              stroke="#C45C3E"
              strokeWidth={1.6}
              dot={false}
              activeDot={{ r: 3, fill: "#C45C3E" }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

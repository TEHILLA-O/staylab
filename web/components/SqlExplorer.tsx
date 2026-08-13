"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { SqlQuery } from "@/types/experiment";

export function SqlExplorer() {
  const [queries, setQueries] = useState<SqlQuery[]>([]);
  const [selected, setSelected] = useState<string>("conversion");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .sql()
      .then((rows) => {
        setQueries(rows);
        if (rows.length) setSelected((current) =>
          rows.some((q) => q.name === current) ? current : rows[0].name,
        );
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const active = queries.find((q) => q.name === selected);

  return (
    <section>
      <h2 className="font-serif text-2xl text-ink">SQL</h2>
      <p className="mt-1 max-w-xl text-sm text-mute">
        The named query that produced the selected metric. Read-only — the API will not
        execute caller-supplied SQL.
      </p>

      {error ? <p className="mt-6 text-sm text-down">{error}</p> : null}

      <div className="mt-6 flex flex-wrap gap-2">
        {queries.map((query) => (
          <button
            key={query.name}
            type="button"
            onClick={() => setSelected(query.name)}
            className={`border px-3 py-1.5 text-xs ${
              selected === query.name
                ? "border-ink bg-ink text-canvas"
                : "border-line text-mute hover:border-ink hover:text-ink"
            }`}
          >
            {query.title}
          </button>
        ))}
      </div>

      {active ? (
        <div className="mt-6">
          <p className="text-sm leading-relaxed text-mute">{active.description}</p>
          <pre className="mt-4 overflow-x-auto border border-line bg-surface p-5 font-mono text-[12px] leading-relaxed text-ink">
            {active.sql.trim()}
          </pre>
        </div>
      ) : null}
    </section>
  );
}

"""Time every query in the SQL library.

Used to catch the case where a dashboard endpoint quietly becomes slow because
a view stopped being materialised or an index was dropped.
"""

from __future__ import annotations

import argparse
import sys
import time

from analytics.db import apply_schema, get_engine, read_query
from analytics.logging_config import get_logger

log = get_logger(__name__)

QUERIES: list[tuple[str, dict]] = [
    ("experiment_summary", {}),
    ("conversion", {}),
    ("daily_metrics", {}),
    ("funnel", {}),
    ("revenue", {}),
    ("guardrails", {}),
    ("sample_ratio_mismatch", {}),
    ("marketplace_overview", {}),
    ("segmentation", {"segment_type": "device", "row_limit": 25}),
    ("segmentation", {"segment_type": "neighbourhood", "row_limit": 25}),
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Benchmark the SQL query library")
    parser.add_argument("--experiment-id", type=int, default=1)
    parser.add_argument("--rebuild-schema", action="store_true",
                        help="re-apply schema.sql (repopulates materialised views)")
    args = parser.parse_args()

    engine = get_engine()
    if args.rebuild_schema:
        started = time.perf_counter()
        apply_schema(engine)
        print(f"schema applied + views materialised in "
              f"{time.perf_counter() - started:.1f}s\n")

    total = 0.0
    slow = 0
    for name, extra in QUERIES:
        params = {"experiment_id": args.experiment_id, **extra}
        started = time.perf_counter()
        frame = read_query(name, params, engine)
        elapsed = (time.perf_counter() - started) * 1000
        total += elapsed
        label = name + (f" [{extra['segment_type']}]" if "segment_type" in extra else "")
        flag = ""
        if elapsed > 1000:
            flag = "  <-- slow"
            slow += 1
        print(f"{label:<34}{elapsed:8.0f}ms{len(frame):>6} rows{flag}")

    print(f"\n{'total':<34}{total:8.0f}ms")
    return 1 if slow else 0


if __name__ == "__main__":
    raise SystemExit(main())

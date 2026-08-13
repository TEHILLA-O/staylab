"""Quick manual smoke test against a running API.

    python tests/smoke_api.py [base_url]

Kept separate from the pytest suite: this one needs a live server and a loaded
database, which CI will not always have.
"""

from __future__ import annotations

import sys
import time

import httpx

PATHS = [
    "/",
    "/health",
    "/experiments",
    "/experiments/EXP-024",
    "/experiments/EXP-024/summary",
    "/experiments/EXP-024/timeseries",
    "/experiments/EXP-024/segments?segment_type=device",
    "/experiments/EXP-024/segments?segment_type=neighbourhood&limit=10",
    "/experiments/EXP-024/funnel",
    "/experiments/EXP-024/statistics",
    "/experiments/EXP-024/analysis",
    "/experiments/EXP-024/marketplace",
    "/experiments/sql",
    "/experiments/sql/conversion",
]

EXPECT_404 = ["/experiments/DOES-NOT-EXIST", "/experiments/sql/not_a_query"]


def main() -> int:
    # Unbuffered so progress is visible while slow endpoints are in flight.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
    failures = 0
    with httpx.Client(base_url=base, timeout=180.0) as client:
        for path in PATHS:
            started = time.perf_counter()
            try:
                response = client.get(path)
                ms = (time.perf_counter() - started) * 1000
                ok = response.status_code == 200
                size = len(response.content)
                print(f"{response.status_code}  {ms:8.0f}ms  {size:>9,}B  {path}")
                if not ok:
                    failures += 1
                    print(f"       body: {response.text[:300]}")
            except Exception as exc:
                failures += 1
                print(f"ERR              {path}: {exc}")

        for path in EXPECT_404:
            response = client.get(path)
            ok = response.status_code == 404
            print(f"{response.status_code}  {'expect 404':>12}          {path}"
                  f"{'' if ok else '  <-- WRONG'}")
            failures += 0 if ok else 1

    print("\nall endpoints healthy" if not failures else f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

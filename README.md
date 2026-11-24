# StayLab

StayLab is an A/B test readout for a redesigned booking flow, built for analysts and hiring managers who want to see experiment analysis done end to end: real Inside Airbnb London listings, a clearly labelled simulated experiment on top, SQL metrics, statistical inference, a FastAPI service and a Next.js dashboard.

It answers one question:

> Does a simplified booking experience increase the probability that a visitor completes a booking?

Engineering notes on what can go wrong, what broke and how it was fixed are in [FAILURES.md](./FAILURES.md).

## What is real, and what is not

**Real.** The Inside Airbnb London snapshot of 19 June 2026: listings, calendar availability and neighbourhoods. Hosts, prices, review scores, room types and boroughs are observed data.

**Simulated.** User assignment, sessions, funnel events and bookings. Inside Airbnb does not publish randomised experiments or booking funnel logs, so StayLab generates a randomised layer with a fixed seed on top of the real listing attributes. Every lift, p-value and revenue figure in this repo comes from that simulated layer. None of it is a measured business result.

Comparing `instant_bookable = true` against `false` and calling it an A/B test would be misleading, because hosts were never randomised into those groups. That is why the experiment layer exists.

## What it does

- Downloads and cleans the Inside Airbnb London snapshot (61,852 of 92,638 listings kept after filtering on the 2026-06-19 snapshot).
- Simulates experiment EXP-024: users are randomised once into Control A or Treatment B, and conversion depends on real listing covariates (price against borough, review score, room type, superhost, instant book) plus device and traffic source. Treatment B gets a small logit-scale effect.
- Loads everything into PostgreSQL, with SQL views and a fixed catalogue of named queries.
- Runs validation checks (sample ratio mismatch, one variant per user, funnel ordering, events reconciling with bookings, A/A check, balance checks).
- Computes the primary metric, secondary metrics, guardrails, funnel and segments, then makes a ship decision. The decision does not rely on `p < 0.05` alone. It also needs the right effect direction, a practically meaningful effect size, a confidence interval that excludes zero, a clean allocation check and intact guardrails.
- Serves the results through a read-only FastAPI service and a Next.js dashboard.

## How it works

```mermaid
flowchart TD
    A[Inside Airbnb London snapshot] --> B[Python ETL]
    B --> C[(PostgreSQL)]
    S[Seeded experiment simulator] --> C
    C --> D[SQL views and named queries]
    D --> E[Python inference: z-test, CI, power, decision]
    E --> F[FastAPI on :8010]
    F --> G[Next.js dashboard]
    E --> H[Terminal readout]
```

SQL answers what happened. Python answers whether the difference is credible. The API only runs the named queries in `database/queries/` and never executes SQL supplied by a caller.

## Quick start

Requires Python 3.11+, Node 20+ and Docker (Compose starts Postgres on port 5434).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

docker compose up -d db

# download, clean listings, simulate the experiment, load Postgres, print the readout
python -m analytics.pipeline --readout

uvicorn api.main:app --port 8010   # API docs at http://localhost:8010/docs

cd web
cp .env.local.example .env.local
npm install
npm run dev                        # dashboard at http://localhost:3000
```

The first pipeline run downloads about 130 MB and scans roughly 34 million calendar rows. On the test machine the whole pipeline, download included, took about 41 seconds. To skip the calendar step on a first pass:

```bash
python -m analytics.etl_listings --skip-calendar
python -m analytics.load_database
```

Availability then falls back to `availability_365` from the listings file. Once data is loaded you can reprint the readout without downloading again:

```bash
python -m analytics.pipeline --skip-download --skip-etl --readout
# or
python -m analytics.run_analysis --segment neighbourhood
```

### Real output

Run on 1 November 2026 against the 2026-06-19 snapshot with the default seed (`EXPERIMENT_SEED=20260619`). The experiment data is simulated, so these numbers show the analysis working, not a real product result. Trimmed for length:

```text
  StayLab | EXP-024 | Simplified booking experience
  RUNNING | 84,746 users | 99,870 sessions | 14 days

EXPERIMENT VALIDATION
  PASS  sample ratio mismatch       42,349 control / 42,397 treatment (50.028% treatment), chi-square p = 0.869.
  PASS  events match bookings       8,918 bookings reconcile with 8,918 booking_completed events.
  ...
  7/7 passed, 0 warning(s), 0 failure(s)

PRIMARY METRIC - booking conversion (per randomised user)
  Control A      9.86%   (4,176 / 42,349)
  Treatment B    10.87%   (4,609 / 42,397)
  Absolute uplift    +1.01 pp
  95% CI (absolute)  [+0.60 pp, +1.42 pp]
  z / p              4.823 / 1.41e-06
  MDE at this n      0.57 pp (+5.82% relative)

GUARDRAILS
  ok      Cancellation rate          0.0816 -> 0.0739   -9.40%
  ok      Checkout abandonment       0.4468 -> 0.4469   +0.02%

DECISION
  Recommendation: SHIP
  Incremental gross bookings (annualised)  £30,027,959
```

The annualised revenue line is a projection from the simulated revenue per visitor, flat traffic and a 15% take rate. The readout itself says it is not a measured outcome.

## Tests

```bash
pytest -m "not integration"     # 42 tests, no database needed
pytest -m integration           # 4 tests, needs a loaded database
ruff check analytics api tests
```

Results on 1 November 2026 (Python 3.12, Postgres 16 in Docker):

| Check | Result |
| --- | --- |
| `pytest -m "not integration"` | 42 passed |
| `pytest -m integration` | 4 passed |
| `ruff check analytics api tests` | 17 findings, all auto-fixable (mostly import order) |
| API endpoints listed below | all returned 200 against the loaded database |
| `npm ci && npm run build` in `web/` | succeeded |

Tests cover random assignment, one variant per user, uplift arithmetic, the z-test, the decision policy, API schemas and the SQL catalogue. There is no CI workflow in this repo, so none of this runs automatically.

## Rigour checks

[docs/RIGOUR.md](docs/RIGOUR.md) adds power planning, a daily sample ratio check with Holm correction, bootstrap intervals, CUPED, multiple testing correction across 40 segments, and an always valid sequential test, plus 600 full simulated reruns to measure error rates. Highlights from 24 November 2026:

- Checking a normal z-test every day and stopping at the first p < 0.05 gave a 17.5% false positive rate in 200 A/A reruns, against 4.5% for a single look and 1.5% for the mSPRT.
- 13 of 40 segment tests were significant before correction, 3 after Holm and 7 after Benjamini-Hochberg.
- CUPED with pre-assignment covariates cut variance by only about 1%, because the simulator has no pre-period metric. This is reported as is.

```bash
python -m analytics.rigour_report --sims 200 --workers 2 --out reports/rigour
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | API and database status |
| GET | `/experiments` | Experiment registry |
| GET | `/experiments/{id}` | Metadata |
| GET | `/experiments/{id}/summary` | Per-variant SQL aggregates |
| GET | `/experiments/{id}/timeseries` | Daily and cumulative conversion |
| GET | `/experiments/{id}/segments` | Device, traffic source, neighbourhood |
| GET | `/experiments/{id}/statistics` | z-test, confidence interval, power |
| GET | `/experiments/{id}/analysis` | Full dashboard payload |
| GET | `/experiments/sql` | Read-only catalogue of the named SQL |

`{id}` can be numeric or the key, for example `EXP-024`.

## Project structure

```text
staylab/
├── analytics/          download, ETL, experiment simulator, statistics, loader, readout
├── api/                FastAPI service
├── database/
│   ├── schema.sql      tables and materialised views
│   └── queries/        the only SQL the API is allowed to run
├── web/                Next.js dashboard
├── tests/              unit and integration tests
├── data/raw/london/    downloaded snapshot (not committed)
├── data/processed/     parquet output from ETL
├── docs/COLUMNS.md     column reference for the source data
├── docker-compose.yml  Postgres on port 5434
└── FAILURES.md
```

## Configuration

Copy `.env.example` to `.env`. The main settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://staylab:staylab@localhost:5434/staylab` | Database connection |
| `INSIDE_AIRBNB_SNAPSHOT` | `2026-06-19` | Which snapshot to download |
| `EXPERIMENT_SEED` | `20260619` | Seed for the simulated experiment |
| `EXPERIMENT_SESSIONS` | `100000` | Target number of simulated sessions |
| `EXPERIMENT_DAYS` | `14` | Experiment length |
| `API_PORT` | `8010` | FastAPI port |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed dashboard origin |

The web app reads `NEXT_PUBLIC_API_BASE_URL` from `web/.env.local`. Do not commit `.env`, `web/.env.local` or anything under `data/raw/`.

## Limitations and known issues

- The experiment is simulated. The treatment effect is built into the generator, so the analysis can only rediscover it. This is a demonstration of method, not evidence about any real booking flow.
- The dashboard build was verified, but the dashboard pages were not checked visually in a browser for this README.
- There is no CI, so tests and lint only run when someone runs them.
- Ruff reports 17 style findings, all auto-fixable.
- Nothing is deployed. A Vercel front end with the API and Postgres on Railway or Render would work, but it has not been set up.
- Fixed while preparing this README: `python -m analytics.pipeline --readout` crashed after loading because the readout parsed the pipeline's arguments, and `GET /experiments` joined every user to every session (about 8.5 billion rows), which filled Postgres temp space and returned 503. Both are fixed in separate commits.

## Troubleshooting

**`Cannot reach PostgreSQL`.** Start Docker, then run `docker compose up -d db`. The project uses port 5434 so it does not collide with a local Postgres on 5432. On Windows, start Docker Desktop first, because Compose hangs if `com.docker.service` is disabled.

**Disk full during `npm install`.** The raw Inside Airbnb files plus `node_modules` are large. Free some space and retry. On Windows the npm cache under `%LOCALAPPDATA%\npm-cache` is safe to delete.

## Status

Working locally end to end: pipeline, readout, API and dashboard build. It is a portfolio project and is not deployed. More of my work is at [cv.omnitest.dev](https://cv.omnitest.dev/).

## Licence

Code is under the [MIT License](./LICENSE). Inside Airbnb data is [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); please credit [insideairbnb.com](https://insideairbnb.com/). The experiment event stream is synthetic and must be described that way if you present this project.

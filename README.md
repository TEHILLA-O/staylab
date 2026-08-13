# StayLab

Experimentation analytics for a redesigned booking experience.

StayLab is a portfolio system that looks like an internal experiment product: real marketplace data, a transparent simulated A/B layer, SQL-first metrics, statistical inference, a FastAPI service, and a Next.js readout.

It answers one business question:

> Does a simplified booking experience increase the probability that a visitor starts a booking?

## What is real, and what is not

**Real.** Inside Airbnb's London snapshot of 19 June 2026: detailed listings, calendar availability, neighbourhoods. Hosts, prices, review scores, room types and boroughs are observed.

**Simulated.** User assignment, sessions, funnel events and bookings. Inside Airbnb does not publish randomised experiments or booking-funnel logs. The README, API and UI all say so.

Comparing `instant_bookable = true` against `false` and calling it an A/B test would be misleading. Hosts were never randomised into those groups. StayLab therefore generates an explicit randomised layer on top of the real listing attributes.

## The experiment

**EXP-024 — Simplified booking experience**

| | Control A | Treatment B |
| --- | --- | --- |
| Surface | Existing booking flow | Nightly rate + all-in total, Reserve CTA |
| Hypothesis | — | B raises booking conversion |

- **H0:** conversion B = conversion A
- **H1:** conversion B ≠ conversion A (two-sided)
- **Unit:** user, assigned once, never both variants
- **Primary metric:** user-level booking conversion
- **Secondary:** CTA click, checkout start, bounce, revenue per visitor, average booking value
- **Guardrail:** cancellation and checkout abandonment

Assignment is `np.random.choice(["A", "B"], p=[0.5, 0.5])`. The split is not forced to 50/50. A sample-ratio-mismatch check tests whether the realised allocation is consistent with chance.

Baseline conversion is a function of real listing and session covariates (price vs borough, review score, room type, superhost, instant book, device, traffic source). Variant B then receives a small logit-scale treatment effect. A fixed seed makes the run reproducible. Dashboard numbers are always computed from stored rows.

## Architecture

```
Inside Airbnb London
        │
   Python ETL
        │
   PostgreSQL
   ├── listings / neighbourhoods     (real)
   └── users / sessions / events / bookings  (simulated)
        │
      SQL views + named queries
        │
   Python inference (z-test, CI, decision)
        │
      FastAPI
        │
   Next.js · StayLab
```

SQL answers *what happened*. Python answers *whether the difference is credible*. The API does not invent metrics and does not execute caller-supplied SQL.

Decision logic does not ship on `p < 0.05` alone. It also requires effect direction, practical magnitude, a confidence interval that excludes zero, a clean allocation check, and intact guardrails.

## Quick start

Requires Python 3.11+, Node 20+, and Docker Desktop (the Compose file starts Postgres). On Windows, start Docker Desktop first — if `com.docker.service` is disabled, Compose will hang and port 5434 will not accept connections.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

docker compose up -d db

python -m analytics.pipeline --readout
# download → clean listings → generate experiment → load Postgres → print readout

uvicorn api.main:app --reload --port 8010

cd web
cp .env.local.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). API docs: [http://localhost:8010/docs](http://localhost:8010/docs).

Raw files are large and are not committed. Re-download with `python -m analytics.download_data`.

Calendar aggregation is the slow step (~30M rows). To skip it on a first pass:

```bash
python -m analytics.etl_listings --skip-calendar
python -m analytics.load_database
```

Availability then falls back to `availability_365` on the listings file.

## Project layout

```
staylab/
├── data/raw/london/          # untouched Inside Airbnb snapshot
├── data/processed/           # parquet from ETL
├── analytics/                # download, ETL, simulator, stats, load
├── database/
│   ├── schema.sql
│   └── queries/              # named SQL the API is allowed to run
├── api/                      # FastAPI
├── web/                      # Next.js dashboard
├── tests/
└── docs/COLUMNS.md
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/experiments` | Registry |
| GET | `/experiments/{id}` | Metadata |
| GET | `/experiments/{id}/summary` | Per-variant SQL aggregates |
| GET | `/experiments/{id}/timeseries` | Daily / cumulative conversion |
| GET | `/experiments/{id}/segments` | Device, traffic, neighbourhood |
| GET | `/experiments/{id}/statistics` | z-test, CI, power |
| GET | `/experiments/{id}/analysis` | Full dashboard payload |
| GET | `/experiments/sql` | Read-only SQL catalogue |

`{id}` may be numeric or `EXP-024`.

## Tests

```bash
pytest -m "not integration"
pytest -m integration          # needs a loaded database
ruff check analytics api tests
```

Covered: random assignment, one variant per user, uplift arithmetic, z-test, decision policy, API schemas, SQL catalogue.

## Deploy

- Frontend: Vercel (`web/`, `NEXT_PUBLIC_API_BASE_URL` pointing at the API)
- API + PostgreSQL: Railway or Render (`docker-compose.yml` is the local analogue)

Do not commit `data/raw/**` or `.env`.

## Troubleshooting

**`Cannot reach PostgreSQL`**  
Start Docker Desktop, then `docker compose up -d db`. This project uses port **5434** so it does not collide with a local Postgres already on 5432.

**Disk full during `npm install`**  
Raw Inside Airbnb files plus `node_modules` are large. Free space, then retry. The npm cache under `%LOCALAPPDATA%\npm-cache` is safe to delete.

## Licence / data

Inside Airbnb data is [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Cite [insideairbnb.com](https://insideairbnb.com/). The experiment event stream is synthetic and must be described as such if you present this project.

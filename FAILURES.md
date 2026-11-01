# Failure modes, fixes, and results

Honest engineering notes for this project. Nothing here is invented for polish.

## What can go wrong

- **Treating `instant_bookable` as an A/B test.** Impact: causal claims on non-random host choices. Mitigation: explicit simulated randomised layer; README/API/UI state what is real vs simulated.
- **Deciding on `p < 0.05` alone.** Impact: shipping a weak or harmful change. Mitigation: require effect direction, practical magnitude, CI excluding zero, sample-ratio-mismatch check, intact guardrails.
- **Caller-supplied SQL through the API.** Impact: injection / metric invention. Mitigation: named queries only; API does not execute arbitrary SQL.
- **Docker/Compose hang on Windows or disk full from raw Airbnb files.** Impact: blocked bootstrap. Mitigation: troubleshooting notes (start Docker service, free space, `--skip-calendar` for ~30M row aggregation).

## What went wrong

1. **`python -m analytics.pipeline --readout` crashed after loading.** `run_analysis.main()` parsed `sys.argv`, so it saw the pipeline's own `--readout` flag and exited with `unrecognized arguments`. Found on 1 November 2026 while testing the quick start.
2. **`GET /experiments` returned 503.** The registry query joined sessions to experiments rather than to users, producing users x sessions rows (about 8.5 billion for EXP-024). Postgres ran out of temp disk space and the API reported the database as unavailable.

The main design failure avoided is observational confounding disguised as experimentation (called out directly in the README).

## How it was resolved

- `run_analysis.main()` now takes an argument list and the pipeline passes an empty one.
- The registry query joins sessions on `user_id`, so each session is counted once. The endpoint now answers in about 0.2 seconds.

- Fixed seed assignment `np.random.choice`, SRM check, logit-scale treatment effect on top of real listing covariates.
- SQL answers what happened; Python inference answers credibility; Next.js readout consumes API metrics only.

## Results

- 1 November 2026: Compose Postgres, `python -m analytics.pipeline --readout`, all FastAPI endpoints on `:8010` and `npm run build` for the dashboard all worked after the two fixes above. 42 unit and 4 integration tests passed. The dashboard was not checked visually in a browser.
- Dashboard numbers always computed from stored rows. No fabricated lift percentages claimed here beyond what a local readout prints after you run the pipeline.

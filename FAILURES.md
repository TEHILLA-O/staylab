# Failure modes, fixes, and results

Honest engineering notes for this project. Nothing here is invented for polish.

## What can go wrong

- **Treating `instant_bookable` as an A/B test.** Impact: causal claims on non-random host choices. Mitigation: explicit simulated randomised layer; README/API/UI state what is real vs simulated.
- **Deciding on `p < 0.05` alone.** Impact: shipping a weak or harmful change. Mitigation: require effect direction, practical magnitude, CI excluding zero, sample-ratio-mismatch check, intact guardrails.
- **Caller-supplied SQL through the API.** Impact: injection / metric invention. Mitigation: named queries only; API does not execute arbitrary SQL.
- **Docker/Compose hang on Windows or disk full from raw Airbnb files.** Impact: blocked bootstrap. Mitigation: troubleshooting notes (start Docker service, free space, `--skip-calendar` for ~30M row aggregation).

## What went wrong

**No recorded production incident in this repo yet.** The main design failure avoided is observational confounding disguised as experimentation (called out directly in the README).

## How it was resolved

- Fixed seed assignment `np.random.choice`, SRM check, logit-scale treatment effect on top of real listing covariates.
- SQL answers what happened; Python inference answers credibility; Next.js readout consumes API metrics only.

## Results

- Successful local demo: Compose Postgres, `python -m analytics.pipeline --readout`, FastAPI `:8010`, Next `:3000`.
- Dashboard numbers always computed from stored rows. No fabricated lift percentages claimed here beyond what a local readout prints after you run the pipeline.

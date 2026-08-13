import Link from "next/link";

export default function MethodologyPage() {
  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-[720px] px-6 py-10 sm:px-10">
        <header className="flex items-baseline justify-between">
          <Link href="/" className="font-serif text-[28px] text-ink">
            StayLab
          </Link>
          <Link href="/" className="text-sm text-mute hover:text-ink">
            Back to EXP-024
          </Link>
        </header>

        <p className="label mt-16">Methodology</p>
        <h1 className="mt-3 font-serif text-4xl leading-tight text-ink">
          How this experiment is read
        </h1>
        <p className="mt-6 text-[17px] leading-relaxed text-mute">
          StayLab is a portfolio analytics system. It uses real London marketplace data and
          a separately generated randomised experiment. The two layers are never mixed up
          in the analysis.
        </p>

        <article className="mt-14 space-y-12 text-[16px] leading-relaxed text-ink">
          <section>
            <h2 className="font-serif text-2xl">Hypothesis</h2>
            <p className="mt-3 text-mute">
              Showing the all-in total price next to the nightly rate, with a clearer
              Reserve call to action, increases the probability that a visitor starts and
              completes a booking.
            </p>
            <dl className="mt-6 space-y-3 text-sm">
              <div>
                <dt className="label">H0</dt>
                <dd className="mt-1">Conversion B = Conversion A</dd>
              </div>
              <div>
                <dt className="label">H1</dt>
                <dd className="mt-1">Conversion B ≠ Conversion A (two-sided test)</dd>
              </div>
            </dl>
            <p className="mt-4 text-sm text-mute">
              The product hypothesis is directional. The test is two-sided so a harmful
              result cannot hide inside a one-sided null.
            </p>
          </section>

          <section>
            <h2 className="font-serif text-2xl">Randomisation</h2>
            <p className="mt-3 text-mute">
              The unit is the user. Assignment is a single Bernoulli draw with p = 0.5,
              once, at first exposure. A user can never appear in both variants — enforced
              in the generator and by a composite foreign key in PostgreSQL. The split is
              not forced to 50/50 after the fact; a sample-ratio-mismatch check tests
              whether the realised allocation is consistent with chance.
            </p>
          </section>

          <section>
            <h2 className="font-serif text-2xl">Metrics</h2>
            <ul className="mt-3 list-disc space-y-2 pl-5 text-mute">
              <li>
                <span className="text-ink">Primary:</span> user-level booking conversion.
                Sessions of the same user are not independent, so the z-test uses users.
              </li>
              <li>
                <span className="text-ink">Secondary:</span> CTA click rate, checkout-start
                rate, session conversion, bounce rate, revenue per visitor, average booking
                value.
              </li>
              <li>
                <span className="text-ink">Guardrails:</span> cancellation rate, checkout
                abandonment, bounce rate. A primary-metric win with a guardrail breach does
                not ship.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-serif text-2xl">Inference</h2>
            <p className="mt-3 text-mute">
              SQL answers what happened. Python answers whether the difference is credible.
              The primary comparison is a two-proportion z-test with a Wald interval on the
              difference and Wilson intervals on each rate. Significance threshold α = 0.05.
            </p>
            <p className="mt-3 text-mute">
              p &lt; 0.05 is not a ship decision. The recommendation also requires a
              positive effect, a confidence interval that excludes zero, a relative lift
              above a practical threshold, a clean sample-ratio check, and intact
              guardrails.
            </p>
          </section>

          <section>
            <h2 className="font-serif text-2xl">Data</h2>
            <p className="mt-3 text-mute">
              Listings and calendar availability come from Inside Airbnb&apos;s London
              snapshot of 19 June 2026. Public Airbnb data does not contain randomised
              assignments or funnel events. Comparing <code>instant_bookable</code> groups
              would not be an experiment: hosts were never randomised.
            </p>
            <p className="mt-3 text-mute">
              The event stream is simulated on top of those real listing attributes. Baseline
              conversion depends on price relative to the borough, review score, room type,
              superhost status, instant booking, device and traffic source. Variant B then
              receives a small, configurable logit shift. A fixed seed makes the run
              reproducible. Nothing on the dashboard is hard-coded.
            </p>
          </section>

          <section>
            <h2 className="font-serif text-2xl">Limitations</h2>
            <ul className="mt-3 list-disc space-y-2 pl-5 text-mute">
              <li>Funnel events are simulated. They are labelled as such in the API and UI.</li>
              <li>
                The treatment effect is designed into the generator. The analysis still has
                to recover it from stored rows the same way it would on production logs.
              </li>
              <li>
                Annualised impact assumes flat traffic and a persistent effect. Novelty in
                the first days means the long-run number is likely lower.
              </li>
              <li>
                Segment lifts on small neighbourhoods are noise. The SQL flags arms under
                1,000 sessions.
              </li>
            </ul>
          </section>
        </article>
      </div>
    </main>
  );
}

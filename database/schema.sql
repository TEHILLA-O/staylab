-- ==========================================================================
-- StayLab — PostgreSQL schema
--
-- Two clearly separated halves:
--   1. Marketplace data  -> real Inside Airbnb London snapshot (listings)
--   2. Experiment data   -> SIMULATED randomised event stream generated on top
--                           of those real listing characteristics
--
-- Inside Airbnb publishes no user-level experiment assignments or funnel
-- events. Everything in the experiment_* / bookings tables is synthetic and is
-- labelled as such in the API and the UI.
--
-- The script is idempotent: safe to run repeatedly.
-- ==========================================================================

-- --------------------------------------------------------------------------
-- 1. Marketplace (real data)
-- --------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS listings (
    listing_id                  BIGINT PRIMARY KEY,
    host_id                     BIGINT,
    neighbourhood               TEXT        NOT NULL,
    latitude                    NUMERIC(9, 6),
    longitude                   NUMERIC(9, 6),
    property_type               TEXT,
    room_type                   TEXT        NOT NULL,
    accommodates                SMALLINT    NOT NULL CHECK (accommodates > 0),
    bedrooms                    SMALLINT,
    beds                        SMALLINT,
    price                       NUMERIC(10, 2) NOT NULL CHECK (price > 0),
    price_per_person            NUMERIC(10, 2),
    neighbourhood_median_price  NUMERIC(10, 2),
    price_vs_neighbourhood      NUMERIC(10, 4),
    minimum_nights              SMALLINT    NOT NULL DEFAULT 1,
    maximum_nights              INTEGER,
    availability_365            SMALLINT,
    number_of_reviews           INTEGER     NOT NULL DEFAULT 0,
    number_of_reviews_ltm       INTEGER     NOT NULL DEFAULT 0,
    reviews_per_month           NUMERIC(8, 2),
    review_scores_rating        NUMERIC(4, 2),
    has_review_score            BOOLEAN     NOT NULL DEFAULT FALSE,
    review_scores_value         NUMERIC(4, 2),
    review_scores_location      NUMERIC(4, 2),
    instant_bookable            BOOLEAN     NOT NULL DEFAULT FALSE,
    host_is_superhost           BOOLEAN     NOT NULL DEFAULT FALSE,
    estimated_occupancy_l365d   SMALLINT,
    last_review                 DATE,
    calendar_availability_rate  NUMERIC(6, 4),
    calendar_avg_price          NUMERIC(10, 2),
    calendar_min_nights         NUMERIC(6, 1)
);

CREATE INDEX IF NOT EXISTS idx_listings_neighbourhood ON listings (neighbourhood);
CREATE INDEX IF NOT EXISTS idx_listings_room_type     ON listings (room_type);

CREATE TABLE IF NOT EXISTS neighbourhoods (
    neighbourhood           TEXT PRIMARY KEY,
    listings                INTEGER NOT NULL,
    median_price            NUMERIC(10, 2),
    avg_price               NUMERIC(10, 2),
    avg_review_score        NUMERIC(4, 2),
    superhost_share         NUMERIC(6, 4),
    instant_bookable_share  NUMERIC(6, 4),
    entire_home_share       NUMERIC(6, 4)
);

-- --------------------------------------------------------------------------
-- 2. Experiment registry
-- --------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id       SERIAL PRIMARY KEY,
    experiment_key      TEXT UNIQUE NOT NULL,
    name                TEXT NOT NULL,
    surface             TEXT NOT NULL DEFAULT 'Booking Flow',
    hypothesis          TEXT NOT NULL,
    primary_metric      TEXT NOT NULL,
    randomisation_unit  TEXT NOT NULL DEFAULT 'user',
    status              TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running', 'completed', 'stopped')),
    control_label       TEXT NOT NULL DEFAULT 'Existing booking experience',
    treatment_label     TEXT NOT NULL DEFAULT 'Simplified booking experience',
    significance_level  NUMERIC(4, 3) NOT NULL DEFAULT 0.05,
    started_at          DATE NOT NULL,
    ended_at            DATE,
    data_source         TEXT NOT NULL DEFAULT 'Inside Airbnb London (listings) + simulated event stream',
    is_simulated        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- --------------------------------------------------------------------------
-- 3. Experiment data (SIMULATED)
-- --------------------------------------------------------------------------

-- Randomisation happens once per user. The composite unique key below is what
-- makes "a user can never appear in two variants" a database-level guarantee
-- rather than a convention.
CREATE TABLE IF NOT EXISTS experiment_users (
    user_id         BIGINT PRIMARY KEY,
    experiment_id   INTEGER NOT NULL REFERENCES experiments (experiment_id) ON DELETE CASCADE,
    variant         CHAR(1) NOT NULL CHECK (variant IN ('A', 'B')),
    assigned_at     TIMESTAMPTZ NOT NULL,
    UNIQUE (user_id, variant)
);

CREATE INDEX IF NOT EXISTS idx_users_variant ON experiment_users (variant);

CREATE TABLE IF NOT EXISTS experiment_sessions (
    session_id          BIGINT PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES experiment_users (user_id) ON DELETE CASCADE,
    experiment_id       INTEGER NOT NULL REFERENCES experiments (experiment_id) ON DELETE CASCADE,
    listing_id          BIGINT NOT NULL REFERENCES listings (listing_id),
    variant             CHAR(1) NOT NULL CHECK (variant IN ('A', 'B')),
    session_started_at  TIMESTAMPTZ NOT NULL,
    device              TEXT NOT NULL CHECK (device IN ('mobile', 'desktop', 'tablet')),
    traffic_source      TEXT NOT NULL,
    is_returning_user   BOOLEAN NOT NULL DEFAULT FALSE,
    -- Enforces variant consistency: the session variant must equal the variant
    -- the user was randomised into.
    FOREIGN KEY (user_id, variant) REFERENCES experiment_users (user_id, variant)
);

CREATE INDEX IF NOT EXISTS idx_sessions_variant  ON experiment_sessions (variant);
CREATE INDEX IF NOT EXISTS idx_sessions_listing  ON experiment_sessions (listing_id);
CREATE INDEX IF NOT EXISTS idx_sessions_started  ON experiment_sessions (session_started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_user     ON experiment_sessions (user_id);

CREATE TABLE IF NOT EXISTS experiment_events (
    event_id        BIGSERIAL PRIMARY KEY,
    session_id      BIGINT NOT NULL REFERENCES experiment_sessions (session_id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL CHECK (event_type IN (
                        'listing_view', 'cta_click', 'checkout_started',
                        'booking_completed', 'session_exit')),
    event_timestamp TIMESTAMPTZ NOT NULL,
    sequence_no     SMALLINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_session ON experiment_events (session_id);
CREATE INDEX IF NOT EXISTS idx_events_type    ON experiment_events (event_type);

CREATE TABLE IF NOT EXISTS bookings (
    booking_id      BIGINT PRIMARY KEY,
    session_id      BIGINT NOT NULL UNIQUE REFERENCES experiment_sessions (session_id) ON DELETE CASCADE,
    listing_id      BIGINT NOT NULL REFERENCES listings (listing_id),
    booking_value   NUMERIC(12, 2) NOT NULL CHECK (booking_value > 0),
    nights          SMALLINT NOT NULL CHECK (nights > 0),
    guests          SMALLINT NOT NULL DEFAULT 1,
    checkin_date    DATE,
    created_at      TIMESTAMPTZ NOT NULL,
    is_cancelled    BOOLEAN NOT NULL DEFAULT FALSE,
    cancelled_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_bookings_listing ON bookings (listing_id);
CREATE INDEX IF NOT EXISTS idx_bookings_created ON bookings (created_at);

-- ==========================================================================
-- 4. Analytical views
--
-- All dashboard numbers are derived from these. Nothing is precomputed into a
-- results table, so the UI can never drift from the underlying event data.
-- ==========================================================================

-- Drop the analytical objects before rebuilding them. PostgreSQL will not let
-- DROP VIEW remove a materialised view or vice versa, so look up what actually
-- exists first. Without this, switching a view between the two kinds turns a
-- rerun of schema.sql into a manual cleanup job.
DO $$
DECLARE
    obj  text;
    kind "char";
BEGIN
    FOREACH obj IN ARRAY ARRAY[
        'experiment_segments',
        'experiment_daily_metrics',
        'experiment_variant_summary',
        'experiment_user_results',
        'experiment_results'
    ] LOOP
        SELECT c.relkind INTO kind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = obj AND n.nspname = current_schema();

        IF kind = 'm' THEN
            EXECUTE format('DROP MATERIALIZED VIEW IF EXISTS %I CASCADE', obj);
        ELSIF kind = 'v' THEN
            EXECUTE format('DROP VIEW IF EXISTS %I CASCADE', obj);
        END IF;
        kind := NULL;
    END LOOP;
END $$;

-- One row per session, with the funnel collapsed into boolean flags.
-- This is the workhorse the rest of the analytics builds on.
--
-- Materialised on purpose. As a plain view, every dashboard request re-scanned
-- ~260k events and re-ran the GROUP BY, which put the main page in the tens of
-- seconds. The event stream only changes when the pipeline reloads, so this is
-- computed once by REFRESH at the end of the load and every downstream query
-- reads it in milliseconds.
CREATE MATERIALIZED VIEW experiment_results AS
WITH funnel AS (
    SELECT
        e.session_id,
        BOOL_OR(e.event_type = 'cta_click')         AS clicked_cta,
        BOOL_OR(e.event_type = 'checkout_started')  AS started_checkout,
        BOOL_OR(e.event_type = 'booking_completed') AS converted,
        COUNT(*)                                    AS event_count,
        MIN(e.event_timestamp)                      AS first_event_at,
        MAX(e.event_timestamp)                      AS last_event_at
    FROM experiment_events e
    GROUP BY e.session_id
)
SELECT
    s.session_id,
    s.user_id,
    s.experiment_id,
    s.listing_id,
    s.variant,
    CASE s.variant WHEN 'A' THEN 'control' ELSE 'treatment' END AS variant_label,
    s.session_started_at,
    (s.session_started_at AT TIME ZONE 'UTC')::date             AS session_date,
    s.device,
    s.traffic_source,
    s.is_returning_user,
    COALESCE(f.clicked_cta, FALSE)       AS clicked_cta,
    COALESCE(f.started_checkout, FALSE)  AS started_checkout,
    COALESCE(f.converted, FALSE)         AS converted,
    -- A bounce is a session that never engaged past the listing view.
    NOT COALESCE(f.clicked_cta, FALSE)   AS bounced,
    -- Abandonment guardrail: reached checkout but never completed.
    (COALESCE(f.started_checkout, FALSE) AND NOT COALESCE(f.converted, FALSE))
                                         AS abandoned_checkout,
    EXTRACT(EPOCH FROM (f.last_event_at - f.first_event_at))::int AS session_seconds,
    b.booking_id,
    COALESCE(b.booking_value, 0)         AS booking_value,
    b.nights,
    COALESCE(b.is_cancelled, FALSE)      AS is_cancelled,
    l.neighbourhood,
    l.room_type,
    l.price                              AS listing_price,
    l.review_scores_rating,
    l.host_is_superhost,
    l.instant_bookable
FROM experiment_sessions s
JOIN listings l              ON l.listing_id = s.listing_id
LEFT JOIN funnel f           ON f.session_id = s.session_id
LEFT JOIN bookings b         ON b.session_id = s.session_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_results_session
    ON experiment_results (session_id);
CREATE INDEX IF NOT EXISTS idx_results_variant
    ON experiment_results (experiment_id, variant);
CREATE INDEX IF NOT EXISTS idx_results_date
    ON experiment_results (experiment_id, session_date);
CREATE INDEX IF NOT EXISTS idx_results_user
    ON experiment_results (user_id);

-- User-level rollup. The randomisation unit is the user, so this is what the
-- primary metric and the significance test are computed from; using sessions
-- would understate variance because sessions of one user are correlated.
CREATE MATERIALIZED VIEW experiment_user_results AS
SELECT
    u.user_id,
    u.experiment_id,
    u.variant,
    u.assigned_at,
    COUNT(r.session_id)                                     AS sessions,
    BOOL_OR(r.clicked_cta)                                  AS clicked_cta,
    BOOL_OR(r.started_checkout)                             AS started_checkout,
    BOOL_OR(r.converted)                                    AS converted,
    BOOL_OR(r.is_cancelled)                                 AS cancelled,
    COALESCE(SUM(r.booking_value), 0)                       AS booking_value,
    COALESCE(SUM(r.booking_value) FILTER (WHERE NOT r.is_cancelled), 0)
                                                            AS net_booking_value,
    MIN(r.session_date)                                     AS first_session_date
FROM experiment_users u
LEFT JOIN experiment_results r ON r.user_id = u.user_id
GROUP BY u.user_id, u.experiment_id, u.variant, u.assigned_at;

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_results_user
    ON experiment_user_results (user_id);
CREATE INDEX IF NOT EXISTS idx_user_results_variant
    ON experiment_user_results (experiment_id, variant);

-- Headline funnel per variant, at both analysis units.
CREATE VIEW experiment_variant_summary AS
WITH sessions AS (
    SELECT
        experiment_id,
        variant,
        COUNT(*)                                    AS sessions,
        COUNT(*) FILTER (WHERE clicked_cta)         AS cta_clicks,
        COUNT(*) FILTER (WHERE started_checkout)    AS checkout_starts,
        COUNT(*) FILTER (WHERE converted)           AS session_conversions,
        COUNT(*) FILTER (WHERE bounced)             AS bounces,
        COUNT(*) FILTER (WHERE abandoned_checkout)  AS checkout_abandons,
        COALESCE(SUM(booking_value), 0)             AS gross_revenue,
        COALESCE(SUM(booking_value) FILTER (WHERE NOT is_cancelled), 0) AS net_revenue,
        COUNT(*) FILTER (WHERE is_cancelled)        AS cancellations
    FROM experiment_results
    GROUP BY experiment_id, variant
),
users AS (
    SELECT
        experiment_id,
        variant,
        COUNT(*)                                AS users,
        COUNT(*) FILTER (WHERE converted)       AS converted_users,
        COUNT(*) FILTER (WHERE clicked_cta)     AS cta_users,
        COUNT(*) FILTER (WHERE started_checkout) AS checkout_users
    FROM experiment_user_results
    GROUP BY experiment_id, variant
)
SELECT
    u.experiment_id,
    u.variant,
    CASE u.variant WHEN 'A' THEN 'control' ELSE 'treatment' END AS variant_label,
    u.users,
    u.converted_users,
    u.cta_users,
    u.checkout_users,
    s.sessions,
    s.cta_clicks,
    s.checkout_starts,
    s.session_conversions,
    s.bounces,
    s.checkout_abandons,
    s.cancellations,
    s.gross_revenue,
    s.net_revenue,
    -- Primary metric: user-level booking conversion.
    ROUND(u.converted_users::numeric / NULLIF(u.users, 0), 6)          AS conversion_rate,
    ROUND(s.session_conversions::numeric / NULLIF(s.sessions, 0), 6)   AS session_conversion_rate,
    ROUND(s.cta_clicks::numeric / NULLIF(s.sessions, 0), 6)            AS cta_click_rate,
    ROUND(s.checkout_starts::numeric / NULLIF(s.sessions, 0), 6)       AS checkout_start_rate,
    ROUND(s.bounces::numeric / NULLIF(s.sessions, 0), 6)               AS bounce_rate,
    ROUND(s.checkout_abandons::numeric / NULLIF(s.checkout_starts, 0), 6)
                                                                       AS checkout_abandon_rate,
    ROUND(s.cancellations::numeric / NULLIF(s.session_conversions, 0), 6)
                                                                       AS cancellation_rate,
    ROUND(s.net_revenue / NULLIF(s.session_conversions, 0), 2)         AS average_booking_value,
    ROUND(s.net_revenue / NULLIF(u.users, 0), 4)                       AS revenue_per_visitor
FROM users u
JOIN sessions s ON s.experiment_id = u.experiment_id AND s.variant = u.variant;

-- Daily and cumulative conversion, computed with window functions so the
-- dashboard chart never has to accumulate anything client-side.
CREATE VIEW experiment_daily_metrics AS
WITH daily AS (
    SELECT
        experiment_id,
        variant,
        session_date,
        COUNT(*)                                AS sessions,
        COUNT(DISTINCT user_id)                 AS users,
        COUNT(*) FILTER (WHERE converted)       AS conversions,
        COUNT(DISTINCT user_id) FILTER (WHERE converted) AS converted_users,
        COALESCE(SUM(booking_value) FILTER (WHERE NOT is_cancelled), 0) AS revenue
    FROM experiment_results
    GROUP BY experiment_id, variant, session_date
)
SELECT
    experiment_id,
    variant,
    CASE variant WHEN 'A' THEN 'control' ELSE 'treatment' END AS variant_label,
    session_date,
    DENSE_RANK() OVER (PARTITION BY experiment_id ORDER BY session_date) AS day_number,
    sessions,
    users,
    conversions,
    revenue,
    ROUND(conversions::numeric / NULLIF(sessions, 0), 6) AS conversion_rate,
    SUM(sessions)    OVER w AS cumulative_sessions,
    SUM(users)       OVER w AS cumulative_users,
    SUM(conversions) OVER w AS cumulative_conversions,
    SUM(revenue)     OVER w AS cumulative_revenue,
    ROUND(
        SUM(conversions) OVER w::numeric / NULLIF(SUM(sessions) OVER w, 0), 6
    ) AS cumulative_conversion_rate
FROM daily
WINDOW w AS (
    PARTITION BY experiment_id, variant
    ORDER BY session_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
);

-- Long-format segment view: one query powers the device / traffic source /
-- neighbourhood switch in the UI.
CREATE VIEW experiment_segments AS
WITH tagged AS (
    SELECT experiment_id, variant, user_id, converted, booking_value, is_cancelled,
           'device' AS segment_type, device AS segment_value
    FROM experiment_results
    UNION ALL
    SELECT experiment_id, variant, user_id, converted, booking_value, is_cancelled,
           'traffic_source', traffic_source
    FROM experiment_results
    UNION ALL
    SELECT experiment_id, variant, user_id, converted, booking_value, is_cancelled,
           'neighbourhood', neighbourhood
    FROM experiment_results
    UNION ALL
    SELECT experiment_id, variant, user_id, converted, booking_value, is_cancelled,
           'room_type', room_type
    FROM experiment_results
)
SELECT
    experiment_id,
    segment_type,
    segment_value,
    variant,
    COUNT(*)                                AS sessions,
    COUNT(DISTINCT user_id)                 AS users,
    COUNT(*) FILTER (WHERE converted)       AS conversions,
    ROUND(COUNT(*) FILTER (WHERE converted)::numeric / NULLIF(COUNT(*), 0), 6)
                                            AS conversion_rate,
    COALESCE(SUM(booking_value) FILTER (WHERE NOT is_cancelled), 0) AS revenue
FROM tagged
GROUP BY experiment_id, segment_type, segment_value, variant;

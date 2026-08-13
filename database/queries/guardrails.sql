-- Guardrail metrics: the things that must not get worse, even if the primary
-- metric improves.
--
-- Each row carries its own direction so the API does not need a hard-coded
-- list of which metrics are "good when up".
WITH per_variant AS (
    SELECT
        variant,
        COUNT(*)                                                AS sessions,
        COUNT(*) FILTER (WHERE converted)                       AS bookings,
        COUNT(*) FILTER (WHERE is_cancelled)                    AS cancellations,
        COUNT(*) FILTER (WHERE bounced)                         AS bounces,
        COUNT(*) FILTER (WHERE abandoned_checkout)              AS checkout_abandons,
        COUNT(*) FILTER (WHERE started_checkout)                AS checkout_starts,
        AVG(session_seconds) FILTER (WHERE session_seconds IS NOT NULL) AS avg_session_seconds
    FROM experiment_results
    WHERE experiment_id = :experiment_id
    GROUP BY variant
),
metrics AS (
    SELECT 'cancellation_rate' AS metric, 'lower_is_better' AS direction,
           variant,
           ROUND(cancellations::numeric / NULLIF(bookings, 0), 6) AS value
    FROM per_variant
    UNION ALL
    SELECT 'checkout_abandon_rate', 'lower_is_better', variant,
           ROUND(checkout_abandons::numeric / NULLIF(checkout_starts, 0), 6)
    FROM per_variant
    UNION ALL
    SELECT 'bounce_rate', 'lower_is_better', variant,
           ROUND(bounces::numeric / NULLIF(sessions, 0), 6)
    FROM per_variant
    UNION ALL
    SELECT 'avg_session_seconds', 'neutral', variant,
           ROUND(avg_session_seconds::numeric, 2)
    FROM per_variant
)
SELECT
    metric,
    direction,
    MAX(value) FILTER (WHERE variant = 'A') AS control_value,
    MAX(value) FILTER (WHERE variant = 'B') AS treatment_value,
    MAX(value) FILTER (WHERE variant = 'B')
        - MAX(value) FILTER (WHERE variant = 'A') AS absolute_change,
    CASE
        WHEN MAX(value) FILTER (WHERE variant = 'A') > 0
        THEN ROUND(
            (MAX(value) FILTER (WHERE variant = 'B')
             - MAX(value) FILTER (WHERE variant = 'A'))
            / MAX(value) FILTER (WHERE variant = 'A'), 6)
    END AS relative_change
FROM metrics
GROUP BY metric, direction
ORDER BY metric;

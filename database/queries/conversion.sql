-- Primary metric: booking conversion by variant.
--
-- Reported at both analysis units. The user-level rate is the one the
-- significance test uses, because the user is the randomisation unit and
-- sessions belonging to the same user are not independent observations.
WITH user_level AS (
    SELECT
        variant,
        COUNT(*)                          AS visitors,
        COUNT(*) FILTER (WHERE converted) AS conversions
    FROM experiment_user_results
    WHERE experiment_id = :experiment_id
    GROUP BY variant
),
session_level AS (
    SELECT
        variant,
        COUNT(DISTINCT session_id)                        AS sessions,
        COUNT(DISTINCT booking_id)                        AS bookings
    FROM experiment_results
    WHERE experiment_id = :experiment_id
    GROUP BY variant
)
SELECT
    u.variant,
    CASE u.variant WHEN 'A' THEN 'Control' ELSE 'Treatment' END AS variant_label,
    u.visitors,
    u.conversions,
    ROUND(u.conversions::numeric / NULLIF(u.visitors, 0), 4) AS conversion_rate,
    s.sessions,
    s.bookings,
    ROUND(s.bookings::numeric / NULLIF(s.sessions, 0), 4)    AS session_conversion_rate
FROM user_level u
JOIN session_level s ON s.variant = u.variant
ORDER BY u.variant;

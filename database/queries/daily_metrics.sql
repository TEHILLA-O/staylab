-- Daily and cumulative conversion per variant, plus the running difference.
--
-- The cumulative series is what the dashboard chart plots: daily rates on
-- ~7,000 sessions bounce around too much to read, while the cumulative curve
-- shows the estimate converging, which is the honest picture of an experiment
-- accumulating evidence.
WITH daily AS (
    SELECT
        variant,
        variant_label,
        session_date,
        day_number,
        sessions,
        users,
        conversions,
        revenue,
        conversion_rate,
        cumulative_sessions,
        cumulative_users,
        cumulative_conversions,
        cumulative_revenue,
        cumulative_conversion_rate
    FROM experiment_daily_metrics
    WHERE experiment_id = :experiment_id
),
spread AS (
    SELECT
        session_date,
        day_number,
        MAX(cumulative_conversion_rate) FILTER (WHERE variant = 'A') AS control_cumulative,
        MAX(cumulative_conversion_rate) FILTER (WHERE variant = 'B') AS treatment_cumulative,
        MAX(conversion_rate)            FILTER (WHERE variant = 'A') AS control_daily,
        MAX(conversion_rate)            FILTER (WHERE variant = 'B') AS treatment_daily,
        SUM(sessions)                                                AS sessions
    FROM daily
    GROUP BY session_date, day_number
)
SELECT
    s.session_date,
    s.day_number,
    s.sessions,
    s.control_daily,
    s.treatment_daily,
    s.control_cumulative,
    s.treatment_cumulative,
    s.treatment_cumulative - s.control_cumulative AS cumulative_absolute_lift,
    CASE
        WHEN s.control_cumulative > 0
        THEN ROUND((s.treatment_cumulative - s.control_cumulative)
                   / s.control_cumulative, 6)
    END AS cumulative_relative_lift
FROM spread s
ORDER BY s.session_date;

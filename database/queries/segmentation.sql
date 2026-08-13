-- Segment comparison: control vs treatment side by side with the lift.
--
-- The same query serves device, traffic source, neighbourhood and room type;
-- the segment dimension is a parameter, not four near-identical queries.
--
-- Segments are ranked by sessions and small ones are flagged rather than
-- hidden: a 40-session neighbourhood showing a "+60% lift" is noise, and the
-- UI needs to be able to say so.
WITH segment AS (
    SELECT
        segment_value,
        variant,
        sessions,
        users,
        conversions,
        conversion_rate,
        revenue
    FROM experiment_segments
    WHERE experiment_id = :experiment_id
      AND segment_type  = :segment_type
),
pivoted AS (
    SELECT
        segment_value,
        SUM(sessions)                                            AS sessions,
        SUM(users)                                               AS users,
        SUM(sessions)    FILTER (WHERE variant = 'A')            AS control_sessions,
        SUM(sessions)    FILTER (WHERE variant = 'B')            AS treatment_sessions,
        SUM(conversions) FILTER (WHERE variant = 'A')            AS control_conversions,
        SUM(conversions) FILTER (WHERE variant = 'B')            AS treatment_conversions,
        SUM(revenue)     FILTER (WHERE variant = 'A')            AS control_revenue,
        SUM(revenue)     FILTER (WHERE variant = 'B')            AS treatment_revenue
    FROM segment
    GROUP BY segment_value
),
rated AS (
    SELECT
        p.*,
        ROUND(control_conversions::numeric   / NULLIF(control_sessions, 0), 6)
            AS control_rate,
        ROUND(treatment_conversions::numeric / NULLIF(treatment_sessions, 0), 6)
            AS treatment_rate
    FROM pivoted p
)
SELECT
    segment_value,
    sessions,
    users,
    control_sessions,
    treatment_sessions,
    control_conversions,
    treatment_conversions,
    control_rate,
    treatment_rate,
    treatment_rate - control_rate AS absolute_lift,
    CASE
        WHEN control_rate > 0
        THEN ROUND((treatment_rate - control_rate) / control_rate, 6)
    END AS relative_lift,
    ROUND(control_revenue, 2)   AS control_revenue,
    ROUND(treatment_revenue, 2) AS treatment_revenue,
    -- Below roughly 1,000 sessions per arm a 1pp effect is indistinguishable
    -- from noise, so mark the row as underpowered instead of dropping it.
    (LEAST(control_sessions, treatment_sessions) < 1000) AS low_sample,
    RANK() OVER (ORDER BY sessions DESC) AS size_rank
FROM rated
ORDER BY sessions DESC
LIMIT :row_limit;

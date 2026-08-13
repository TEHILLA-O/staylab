-- Step-by-step funnel with per-step drop-off.
--
-- Where in the flow the treatment actually helped. A redesign that raises
-- conversion by lifting the CTA click rate is a different product story from
-- one that raises it by reducing checkout abandonment, and the summary metric
-- alone cannot tell them apart.
WITH steps AS (
    SELECT
        variant,
        COUNT(*)                                    AS listing_view,
        COUNT(*) FILTER (WHERE clicked_cta)         AS cta_click,
        COUNT(*) FILTER (WHERE started_checkout)    AS checkout_started,
        COUNT(*) FILTER (WHERE converted)           AS booking_completed
    FROM experiment_results
    WHERE experiment_id = :experiment_id
    GROUP BY variant
),
unpivoted AS (
    SELECT variant, 1 AS step_order, 'listing_view'      AS step, listing_view      AS sessions, listing_view AS entered FROM steps
    UNION ALL
    SELECT variant, 2, 'cta_click',         cta_click,         listing_view     FROM steps
    UNION ALL
    SELECT variant, 3, 'checkout_started',  checkout_started,  cta_click        FROM steps
    UNION ALL
    SELECT variant, 4, 'booking_completed', booking_completed, checkout_started FROM steps
),
rates AS (
    SELECT
        variant,
        step_order,
        step,
        sessions,
        entered,
        ROUND(sessions::numeric / NULLIF(entered, 0), 6) AS step_conversion_rate,
        ROUND(
            sessions::numeric / NULLIF(
                FIRST_VALUE(sessions) OVER (
                    PARTITION BY variant ORDER BY step_order
                ), 0
            ), 6
        ) AS cumulative_conversion_rate
    FROM unpivoted
)
SELECT
    step_order,
    step,
    MAX(sessions)                   FILTER (WHERE variant = 'A') AS control_sessions,
    MAX(sessions)                   FILTER (WHERE variant = 'B') AS treatment_sessions,
    MAX(step_conversion_rate)       FILTER (WHERE variant = 'A') AS control_step_rate,
    MAX(step_conversion_rate)       FILTER (WHERE variant = 'B') AS treatment_step_rate,
    MAX(cumulative_conversion_rate) FILTER (WHERE variant = 'A') AS control_cumulative_rate,
    MAX(cumulative_conversion_rate) FILTER (WHERE variant = 'B') AS treatment_cumulative_rate,
    CASE
        WHEN MAX(step_conversion_rate) FILTER (WHERE variant = 'A') > 0
        THEN ROUND(
            (MAX(step_conversion_rate) FILTER (WHERE variant = 'B')
             - MAX(step_conversion_rate) FILTER (WHERE variant = 'A'))
            / MAX(step_conversion_rate) FILTER (WHERE variant = 'A'), 6)
    END AS step_relative_lift
FROM rates
GROUP BY step_order, step
ORDER BY step_order;

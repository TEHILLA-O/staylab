-- Headline experiment summary: one row per variant plus everything the hero
-- section of the dashboard needs, pivoted against control with window
-- functions so the uplift is computed in SQL rather than in the API layer.
WITH variant_metrics AS (
    SELECT *
    FROM experiment_variant_summary
    WHERE experiment_id = :experiment_id
),
with_baseline AS (
    SELECT
        v.*,
        -- FIRST_VALUE over the variant ordering pins control as the baseline
        -- for every row, which is what makes the lift columns below possible
        -- without a self-join.
        FIRST_VALUE(v.conversion_rate)      OVER w AS baseline_conversion_rate,
        FIRST_VALUE(v.cta_click_rate)       OVER w AS baseline_cta_click_rate,
        FIRST_VALUE(v.checkout_start_rate)  OVER w AS baseline_checkout_start_rate,
        FIRST_VALUE(v.revenue_per_visitor)  OVER w AS baseline_revenue_per_visitor,
        FIRST_VALUE(v.average_booking_value) OVER w AS baseline_average_booking_value,
        FIRST_VALUE(v.bounce_rate)          OVER w AS baseline_bounce_rate,
        FIRST_VALUE(v.cancellation_rate)    OVER w AS baseline_cancellation_rate,
        SUM(v.users)    OVER () AS total_users,
        SUM(v.sessions) OVER () AS total_sessions
    FROM variant_metrics v
    WINDOW w AS (ORDER BY v.variant ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
)
SELECT
    variant,
    variant_label,
    users,
    sessions,
    converted_users,
    session_conversions   AS conversions,
    cta_clicks,
    checkout_starts,
    bounces,
    cancellations,
    checkout_abandons,
    gross_revenue,
    net_revenue,
    conversion_rate,
    session_conversion_rate,
    cta_click_rate,
    checkout_start_rate,
    bounce_rate,
    checkout_abandon_rate,
    cancellation_rate,
    average_booking_value,
    revenue_per_visitor,
    total_users,
    total_sessions,
    ROUND(users::numeric / NULLIF(total_users, 0), 6) AS allocation_share,
    conversion_rate - baseline_conversion_rate        AS conversion_absolute_uplift,
    CASE
        WHEN baseline_conversion_rate > 0
        THEN ROUND((conversion_rate - baseline_conversion_rate)
                   / baseline_conversion_rate, 6)
    END AS conversion_relative_uplift,
    CASE
        WHEN baseline_cta_click_rate > 0
        THEN ROUND((cta_click_rate - baseline_cta_click_rate)
                   / baseline_cta_click_rate, 6)
    END AS cta_relative_uplift,
    CASE
        WHEN baseline_checkout_start_rate > 0
        THEN ROUND((checkout_start_rate - baseline_checkout_start_rate)
                   / baseline_checkout_start_rate, 6)
    END AS checkout_relative_uplift,
    CASE
        WHEN baseline_revenue_per_visitor > 0
        THEN ROUND((revenue_per_visitor - baseline_revenue_per_visitor)
                   / baseline_revenue_per_visitor, 6)
    END AS revenue_per_visitor_relative_uplift,
    CASE
        WHEN baseline_average_booking_value > 0
        THEN ROUND((average_booking_value - baseline_average_booking_value)
                   / baseline_average_booking_value, 6)
    END AS average_booking_value_relative_uplift,
    CASE
        WHEN baseline_bounce_rate > 0
        THEN ROUND((bounce_rate - baseline_bounce_rate) / baseline_bounce_rate, 6)
    END AS bounce_rate_relative_uplift,
    CASE
        WHEN baseline_cancellation_rate > 0
        THEN ROUND((cancellation_rate - baseline_cancellation_rate)
                   / baseline_cancellation_rate, 6)
    END AS cancellation_rate_relative_uplift
FROM with_baseline
ORDER BY variant;

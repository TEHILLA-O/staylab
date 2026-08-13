-- Revenue metrics by variant.
--
-- Cancelled bookings are excluded from net revenue but kept in gross so the
-- gap between the two is visible; a treatment that books more and cancels
-- more is not actually winning.
WITH booking_stats AS (
    SELECT
        r.variant,
        COUNT(*) FILTER (WHERE r.converted)                     AS bookings,
        COUNT(*) FILTER (WHERE r.is_cancelled)                  AS cancellations,
        COALESCE(SUM(r.booking_value), 0)                       AS gross_revenue,
        COALESCE(SUM(r.booking_value) FILTER (WHERE NOT r.is_cancelled), 0)
                                                                AS net_revenue,
        AVG(r.booking_value) FILTER (WHERE r.converted AND NOT r.is_cancelled)
                                                                AS average_booking_value,
        STDDEV_SAMP(r.booking_value) FILTER (WHERE r.converted AND NOT r.is_cancelled)
                                                                AS booking_value_stddev,
        AVG(r.nights) FILTER (WHERE r.converted)                AS average_nights
    FROM experiment_results r
    WHERE r.experiment_id = :experiment_id
    GROUP BY r.variant
),
-- Revenue per visitor has to be spread across every randomised user, including
-- the ones who never booked, otherwise it is just average order value again.
visitor_revenue AS (
    SELECT
        variant,
        COUNT(*)                                AS visitors,
        AVG(net_booking_value)                  AS revenue_per_visitor,
        STDDEV_SAMP(net_booking_value)          AS revenue_per_visitor_stddev
    FROM experiment_user_results
    WHERE experiment_id = :experiment_id
    GROUP BY variant
)
SELECT
    v.variant,
    CASE v.variant WHEN 'A' THEN 'Control' ELSE 'Treatment' END AS variant_label,
    v.visitors,
    b.bookings,
    b.cancellations,
    ROUND(b.gross_revenue, 2)                       AS gross_revenue,
    ROUND(b.net_revenue, 2)                         AS net_revenue,
    ROUND(b.average_booking_value, 2)               AS average_booking_value,
    ROUND(b.booking_value_stddev, 2)                AS booking_value_stddev,
    ROUND(b.average_nights, 2)                      AS average_nights,
    ROUND(v.revenue_per_visitor, 4)                 AS revenue_per_visitor,
    ROUND(v.revenue_per_visitor_stddev, 4)          AS revenue_per_visitor_stddev
FROM visitor_revenue v
JOIN booking_stats b ON b.variant = v.variant
ORDER BY v.variant;

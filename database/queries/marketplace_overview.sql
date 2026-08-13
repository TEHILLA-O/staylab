-- Context on the underlying real marketplace data.
--
-- Nothing here is simulated: these are the Inside Airbnb London listings the
-- experiment sampled its traffic from. Shown in the UI so the split between
-- real marketplace data and the simulated event layer stays visible.
WITH exposure AS (
    SELECT
        listing_id,
        COUNT(*) AS sessions
    FROM experiment_sessions
    WHERE experiment_id = :experiment_id
    GROUP BY listing_id
),
totals AS (
    SELECT
        COUNT(*)                                        AS listings,
        COUNT(DISTINCT neighbourhood)                   AS neighbourhoods,
        ROUND(AVG(price), 2)                            AS avg_price,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price)::numeric, 2)
                                                        AS median_price,
        ROUND(AVG(review_scores_rating), 3)             AS avg_review_score,
        ROUND(AVG(host_is_superhost::int)::numeric, 4)  AS superhost_share,
        ROUND(AVG(instant_bookable::int)::numeric, 4)   AS instant_bookable_share
    FROM listings
)
SELECT
    t.listings,
    t.neighbourhoods,
    t.avg_price,
    t.median_price,
    t.avg_review_score,
    t.superhost_share,
    t.instant_bookable_share,
    (SELECT COUNT(*) FROM exposure)                     AS listings_with_traffic,
    (SELECT ROUND(AVG(sessions), 2) FROM exposure)      AS avg_sessions_per_listing,
    (SELECT MAX(sessions) FROM exposure)                AS max_sessions_per_listing
FROM totals t;

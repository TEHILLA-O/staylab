-- Sample ratio mismatch check.
--
-- Before reading any result, verify the split is what the assignment code
-- claims it is. A skewed split almost always means a bug (bot filtering,
-- redirect loss, a crash in one variant) and it silently biases every metric,
-- so this runs first and can veto the whole readout.
--
-- The chi-square p-value is computed in Python; SQL supplies the counts and a
-- quick z-approximation so the check is meaningful even straight from psql.
WITH counts AS (
    SELECT
        COUNT(*)                                  AS total_users,
        COUNT(*) FILTER (WHERE variant = 'A')     AS control_users,
        COUNT(*) FILTER (WHERE variant = 'B')     AS treatment_users
    FROM experiment_users
    WHERE experiment_id = :experiment_id
),
sessions AS (
    SELECT
        COUNT(*)                                  AS total_sessions,
        COUNT(*) FILTER (WHERE variant = 'A')     AS control_sessions,
        COUNT(*) FILTER (WHERE variant = 'B')     AS treatment_sessions
    FROM experiment_sessions
    WHERE experiment_id = :experiment_id
),
-- Integrity check: the composite foreign key on experiment_sessions makes a
-- user in two variants impossible, but assert it anyway. A schema constraint
-- you never test is a comment.
contamination AS (
    SELECT COUNT(*) AS users_in_both_variants
    FROM (
        SELECT user_id
        FROM experiment_sessions
        WHERE experiment_id = :experiment_id
        GROUP BY user_id
        HAVING COUNT(DISTINCT variant) > 1
    ) AS offenders
)
SELECT
    c.total_users,
    c.control_users,
    c.treatment_users,
    ROUND(c.treatment_users::numeric / NULLIF(c.total_users, 0), 6) AS observed_ratio,
    0.5                                                             AS expected_ratio,
    s.total_sessions,
    s.control_sessions,
    s.treatment_sessions,
    x.users_in_both_variants,
    -- Normal approximation to the binomial: |observed - expected| in SDs.
    ROUND(
        ABS(c.treatment_users - c.total_users / 2.0)
        / NULLIF(SQRT(c.total_users * 0.5 * 0.5), 0), 4
    ) AS allocation_z_score
FROM counts c
CROSS JOIN sessions s
CROSS JOIN contamination x;

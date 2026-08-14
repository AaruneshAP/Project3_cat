-- =============================================================================
-- queries.sql
-- Analytical SQL queries for NLP Maintenance Log Classification (Project 3)
-- Target Table: tickets
-- Database: Neon / Supabase PostgreSQL
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Category Frequency Over Time
-- Description: Counts tickets per predicted_category, grouped by calendar week
-- (using DATE_TRUNC on created_at), ordered by week. Helps monitor overall volume
-- trends and detect long-term shifts in maintenance log failure distributions.
-- -----------------------------------------------------------------------------
SELECT
    DATE_TRUNC('week', created_at)::DATE AS week_start,
    predicted_category,
    COUNT(*) AS ticket_count
FROM tickets
GROUP BY week_start, predicted_category
ORDER BY week_start ASC, predicted_category ASC;


-- -----------------------------------------------------------------------------
-- 2. Low-Confidence Review Queue
-- Description: Retrieves all tickets where model prediction confidence is below
-- 0.70 (70%), ordered by confidence ascending. Serves as a human-in-the-loop
-- review queue for technician validation of ambiguous failure descriptions.
-- -----------------------------------------------------------------------------
SELECT
    id,
    text,
    predicted_category,
    confidence,
    equipment_id,
    created_at
FROM tickets
WHERE confidence < 0.70
ORDER BY confidence ASC;


-- -----------------------------------------------------------------------------
-- 3. Category Breakdown by Equipment
-- Description: Counts tickets per equipment_id per predicted_category.
-- Identifies which specific equipment units experience which failure types most
-- frequently to support predictive maintenance scheduling and root-cause analysis.
-- -----------------------------------------------------------------------------
SELECT
    equipment_id,
    predicted_category,
    COUNT(*) AS ticket_count
FROM tickets
GROUP BY equipment_id, predicted_category
ORDER BY equipment_id ASC, ticket_count DESC;


-- -----------------------------------------------------------------------------
-- 4. Trending Categories
-- Description: Uses the LAG() window function to compare ticket counts for each
-- category between the most recent 30-day window and the prior 30-day window.
-- Calculates absolute net change and percentage change to pinpoint emerging or declining failure trends.
-- -----------------------------------------------------------------------------
WITH category_list AS (
    SELECT DISTINCT predicted_category FROM tickets
),
periods AS (
    SELECT 1 AS period_id UNION ALL SELECT 2 AS period_id
),
cat_periods AS (
    SELECT c.predicted_category, p.period_id
    FROM category_list c CROSS JOIN periods p
),
ticket_periods AS (
    SELECT
        predicted_category,
        CASE
            WHEN created_at >= (SELECT MAX(created_at) FROM tickets) - INTERVAL '30 days' THEN 2
            WHEN created_at >= (SELECT MAX(created_at) FROM tickets) - INTERVAL '60 days'
             AND created_at <  (SELECT MAX(created_at) FROM tickets) - INTERVAL '30 days' THEN 1
        END AS period_id
    FROM tickets
),
actual_counts AS (
    SELECT predicted_category, period_id, COUNT(*) AS ticket_count
    FROM ticket_periods
    WHERE period_id IS NOT NULL
    GROUP BY predicted_category, period_id
),
full_counts AS (
    SELECT
        cp.predicted_category,
        cp.period_id,
        COALESCE(ac.ticket_count, 0) AS ticket_count
    FROM cat_periods cp
    LEFT JOIN actual_counts ac ON cp.predicted_category = ac.predicted_category AND cp.period_id = ac.period_id
),
windowed_trends AS (
    SELECT
        predicted_category,
        period_id,
        ticket_count AS recent_30_days_count,
        LAG(ticket_count) OVER (PARTITION BY predicted_category ORDER BY period_id ASC) AS prior_30_days_count
    FROM full_counts
)
SELECT
    predicted_category,
    prior_30_days_count,
    recent_30_days_count,
    recent_30_days_count - prior_30_days_count AS net_change,
    ROUND(
        ((recent_30_days_count - prior_30_days_count)::NUMERIC / NULLIF(prior_30_days_count, 0)) * 100,
        2
    ) AS pct_change
FROM windowed_trends
WHERE period_id = 2
ORDER BY pct_change DESC NULLS LAST;


-- -----------------------------------------------------------------------------
-- 5. Model Accuracy Check
-- Description: Aggregates overall accuracy and per-category accuracy directly
-- from the database by comparing predicted_category against ground truth true_category.
-- Uses ROLLUP to provide a single summary table validating prediction quality.
-- Note: This measures end-to-end pipeline correctness against the full dataset
-- (including training data), not model generalization — the true out-of-sample test
-- performance is documented separately in results/model_choice_rationale.md.
-- -----------------------------------------------------------------------------
SELECT
    COALESCE(true_category, 'OVERALL TOTAL') AS category,
    COUNT(*) AS total_tickets,
    SUM(CASE WHEN predicted_category = true_category THEN 1 ELSE 0 END) AS correct_predictions,
    ROUND(
        (100.0 * SUM(CASE WHEN predicted_category = true_category THEN 1 ELSE 0 END)) / COUNT(*),
        2
    ) AS accuracy_pct
FROM tickets
GROUP BY ROLLUP(true_category)
ORDER BY
    CASE WHEN true_category IS NULL THEN 1 ELSE 0 END,
    accuracy_pct DESC;

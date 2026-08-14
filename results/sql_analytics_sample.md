# SQL Analytical Queries & Sample Output

This document details the analytical SQL queries defined in [`queries.sql`](file:///e:/Antigravity-x64/Project2_cat/queries.sql) executed against the live PostgreSQL `tickets` database table (4,000 records). Each query addresses a specific operational requirement for maintenance management, automated triage, or model quality monitoring.

---

## 1. Category Frequency Over Time

### Description
Groups maintenance ticket predictions by week (`DATE_TRUNC('week', created_at)`) and `predicted_category`. This enables maintenance managers to monitor overall volume trends and detect macro-level shifts in equipment failure patterns over time.

### SQL Query
```sql
SELECT
    DATE_TRUNC('week', created_at)::DATE AS week_start,
    predicted_category,
    COUNT(*) AS ticket_count
FROM tickets
GROUP BY week_start, predicted_category
ORDER BY week_start ASC, predicted_category ASC;
```

### Sample Output (Representative Subset — First 16 Rows of 112 Total)
| week_start | predicted_category | ticket_count |
| :--- | :--- | :--- |
| `2026-05-11` | bearing_failure | 11 |
| `2026-05-11` | corrosion | 5 |
| `2026-05-11` | electrical_fault | 12 |
| `2026-05-11` | hydraulic_leak | 11 |
| `2026-05-11` | overheating | 6 |
| `2026-05-11` | sensor_malfunction | 10 |
| `2026-05-11` | software_control_fault | 3 |
| `2026-05-11` | wear_and_tear | 7 |
| `2026-05-18` | bearing_failure | 35 |
| `2026-05-18` | corrosion | 40 |
| `2026-05-18` | electrical_fault | 38 |
| `2026-05-18` | hydraulic_leak | 30 |
| `2026-05-18` | overheating | 37 |
| `2026-05-18` | sensor_malfunction | 37 |
| `2026-05-18` | software_control_fault | 40 |
| `2026-05-18` | wear_and_tear | 38 |

---

## 2. Low-Confidence Review Queue

### Description
Filters tickets where the classifier prediction confidence is below `0.70` (70%), sorted in ascending order of confidence. Serves as an automated human-in-the-loop triage queue, routing ambiguous, noisy, or borderline descriptions to senior technicians for manual review.

### SQL Query
```sql
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
```

### Sample Output (Top 10 Lowest-Confidence Records out of 149 Total Flagged)
| id | equipment_id | predicted_category | confidence | created_at | text (snippet) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **2579** | EQ-112 | overheating | **0.3282** | 2026-07-15 04:14 | *Conveyor photoeye blocked by debris, line stopped...* |
| **3608** | EQ-109 | wear_and_tear | **0.3320** | 2026-07-04 04:39 | *Deaerator level control valve plug eroded by wire-drawing, passing steam...* |
| **1636** | EQ-110 | overheating | **0.4132** | 2026-06-16 09:00 | *Hydraulic press main cylinder packing gland leaking and running warm...* |
| **2975** | EQ-118 | sensor_malfunction | **0.4354** | 2026-05-24 01:23 | *Conveyor 3 photo eye blocked/faulty, keeps throwing false jam alarms...* |
| **3613** | EQ-113 | sensor_malfunction | **0.4498** | 2026-08-01 00:35 | *Stacker crane hoist cable showing broken outer wires and diameter reduction...* |
| **1799** | EQ-102 | bearing_failure | **0.4684** | 2026-05-21 15:25 | *Secondary cooling pump outboard bearing housing at 190°F due to failed...* |
| **3547** | EQ-116 | wear_and_tear | **0.4726** | 2026-08-01 12:04 | *Pneumatic slide gate cylinder rod seals blown, pneumatic pressure bleeding...* |
| **2790** | EQ-118 | overheating | **0.4755** | 2026-07-28 00:55 | *Paint line oven exhaust draft gauge pneumatic line plugged with soot...* |
| **2543** | EQ-103 | sensor_malfunction | **0.4882** | 2026-07-10 14:01 | *Rotary kiln drive motor bearing accelerometer cable severed by falling...* |
| **2552** | EQ-101 | software_control_fault | **0.4890** | 2026-07-30 20:43 | *Elevator pit sump pump level float tangled, failing to trigger auto-start...* |

---

## 3. Category Breakdown by Equipment

### Description
Aggregates ticket counts by `equipment_id` and `predicted_category`. This allows reliability engineers to identify specific machinery units prone to repeating failure modes (e.g., hydraulic leaks vs. bearing failures).

### SQL Query
```sql
SELECT
    equipment_id,
    predicted_category,
    COUNT(*) AS ticket_count
FROM tickets
GROUP BY equipment_id, predicted_category
ORDER BY equipment_id ASC, ticket_count DESC;
```

### Sample Output (Representative Subset — First 16 Rows of 160 Total)
| equipment_id | predicted_category | ticket_count |
| :--- | :--- | :--- |
| **EQ-101** | hydraulic_leak | 25 |
| **EQ-101** | wear_and_tear | 24 |
| **EQ-101** | software_control_fault | 24 |
| **EQ-101** | electrical_fault | 21 |
| **EQ-101** | bearing_failure | 21 |
| **EQ-101** | sensor_malfunction | 21 |
| **EQ-101** | corrosion | 17 |
| **EQ-101** | overheating | 13 |
| **EQ-102** | corrosion | 32 |
| **EQ-102** | wear_and_tear | 30 |
| **EQ-102** | bearing_failure | 28 |
| **EQ-102** | overheating | 27 |
| **EQ-102** | software_control_fault | 24 |
| **EQ-102** | electrical_fault | 22 |
| **EQ-102** | hydraulic_leak | 19 |
| **EQ-102** | sensor_malfunction | 18 |

---

## 4. Trending Categories

### Description
Leverages the PostgreSQL `LAG()` window function across defined 30-day time windows (`recent 30 days` vs. `prior 30 days`) to compute net volume changes and percentage velocity changes per failure category.

### SQL Query
```sql
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
```

### Complete Output (All 8 Categories)
| predicted_category | prior_30_days_count | recent_30_days_count | net_change | pct_change (%) |
| :--- | :--- | :--- | :--- | :--- |
| **electrical_fault** | 161 | 177 | +16 | **+9.94%** |
| **software_control_fault** | 170 | 173 | +3 | **+1.76%** |
| **corrosion** | 170 | 172 | +2 | **+1.18%** |
| **bearing_failure** | 171 | 165 | -6 | **-3.51%** |
| **wear_and_tear** | 169 | 161 | -8 | **-4.73%** |
| **overheating** | 166 | 158 | -8 | **-4.82%** |
| **hydraulic_leak** | 189 | 160 | -29 | **-15.34%** |
| **sensor_malfunction** | 181 | 150 | -31 | **-17.13%** |

> [!NOTE]
> **Data Generation Disclaimer:** Ticket creation timestamps were generated synthetically using uniform random distribution across the past 90 days (`load_predictions.py`). Consequently, the specific percentage changes shown above reflect synthetic random variance and demonstrate SQL query logic/window function capability rather than a real-world physical failure trend.

---

## 5. Model Accuracy Check

### Description
Compares `predicted_category` against ground-truth `true_category` directly inside PostgreSQL using `GROUP BY ROLLUP(true_category)`. Provides per-category accuracy and total dataset pipeline match rate in a single query result.

### SQL Query
```sql
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
```

### Complete Output (All 8 Categories + Overall Summary)
| category | total_tickets | correct_predictions | accuracy_pct (%) |
| :--- | :--- | :--- | :--- |
| **hydraulic_leak** | 500 | 498 | **99.60%** |
| **electrical_fault** | 500 | 497 | **99.40%** |
| **bearing_failure** | 500 | 497 | **99.40%** |
| **software_control_fault** | 500 | 496 | **99.20%** |
| **corrosion** | 500 | 496 | **99.20%** |
| **sensor_malfunction** | 500 | 491 | **98.20%** |
| **wear_and_tear** | 500 | 489 | **97.80%** |
| **overheating** | 500 | 483 | **96.60%** |
| **OVERALL TOTAL** | **4000** | **3947** | **98.68%** |

> [!IMPORTANT]
> **Pipeline Verification vs. Model Generalization:** This database query evaluates pipeline end-to-end correctness and seed data integrity across the entire 4,000-ticket dataset (which includes training samples). It is intended as a SQL database sanity check to confirm loaded predictions match model outputs. True out-of-sample model generalization (held-out test set performance of **94.6% Macro F1 / 94.7% Accuracy**) is documented separately in [`model_choice_rationale.md`](file:///e:/Antigravity-x64/Project2_cat/results/model_choice_rationale.md).

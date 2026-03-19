"""
BigQuery SQL (with CTEs) for querying Motive Insights export data.

Assume the CSV is loaded into a table, e.g.:
  `your_project.your_dataset.motive_insights_daily`

Columns: date, Name, Email, Department, Title, Manager,
  Days active in period, Searches in period, Assistant actions in period,
  Agent runs in period, Active client sessions in period
"""

BIGQUERY_SQL = """
-- Replace `your_project.your_dataset.motive_insights_daily` with your table.
WITH raw AS (
  SELECT
    PARSE_DATE('%Y-%m-%d', date) AS date,
    Name,
    Email,
    Department,
    Title,
    Manager,
    `Days active in period`     AS days_active,
    `Searches in period`       AS searches,
    `Assistant actions in period` AS assistant_actions,
    `Agent runs in period`     AS agent_runs,
    `Active client sessions in period` AS active_sessions
  FROM `your_project.your_dataset.motive_insights_daily`
  WHERE date IS NOT NULL
),

-- Only rows with at least one activity metric (matches script's filter).
with_activity AS (
  SELECT *
  FROM raw
  WHERE (days_active + searches + assistant_actions + agent_runs + active_sessions) > 0
),

-- Daily totals (all users) for a quick summary.
daily_totals AS (
  SELECT
    date,
    COUNT(*) AS active_users,
    SUM(searches) AS total_searches,
    SUM(assistant_actions) AS total_assistant_actions,
    SUM(agent_runs) AS total_agent_runs,
    SUM(active_sessions) AS total_sessions
  FROM with_activity
  GROUP BY date
),

-- Per-department rollup by date.
by_department AS (
  SELECT
    date,
    Department AS department,
    COUNT(*) AS users,
    SUM(searches) AS searches,
    SUM(assistant_actions) AS assistant_actions,
    SUM(agent_runs) AS agent_runs
  FROM with_activity
  GROUP BY date, Department
)

-- Example: daily summary + top departments by searches.
SELECT
  d.date,
  d.active_users,
  d.total_searches,
  d.total_assistant_actions,
  d.total_agent_runs,
  b.department,
  b.users AS dept_users,
  b.searches AS dept_searches
FROM daily_totals d
LEFT JOIN (
  SELECT * FROM by_department
  WHERE TRUE
  QUALIFY ROW_NUMBER() OVER (PARTITION BY date ORDER BY searches DESC) <= 5
) b ON b.date = d.date
ORDER BY d.date DESC, b.searches DESC;
"""

# Simpler example: just list active users and metrics for a date range.
BIGQUERY_SQL_SIMPLE = """
WITH base AS (
  SELECT
    PARSE_DATE('%Y-%m-%d', date) AS date,
    Name,
    Email,
    Department,
    Title,
    Manager,
    `Days active in period`     AS days_active,
    `Searches in period`       AS searches,
    `Assistant actions in period` AS assistant_actions,
    `Agent runs in period`     AS agent_runs,
    `Active client sessions in period` AS active_sessions
  FROM `your_project.your_dataset.motive_insights_daily`
  WHERE date BETWEEN '2026-01-01' AND '2026-03-31'
),
active_only AS (
  SELECT *
  FROM base
  WHERE (days_active + searches + assistant_actions + agent_runs + active_sessions) > 0
)
SELECT * FROM active_only
ORDER BY date DESC, searches DESC;
"""

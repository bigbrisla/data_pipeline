CREATE OR REPLACE VIEW `{project}.analytics.budget_vs_spend` AS
WITH budget AS (
  SELECT
    month_start,
    country,
    engine,
    SUM(IF(is_initial_version, allocated_budget, 0)) AS budget_initial,
    SUM(IF(is_latest_version, allocated_budget, 0)) AS budget_current,
    SUM(IF(is_initial_version, forecasted_purchases, 0)) AS forecasted_purchases,
    SUM(IF(is_initial_version, forecasted_revenues, 0)) AS forecasted_revenues,
    STRING_AGG(DISTINCT campaign_type, ', ') AS campaign_types,
    STRING_AGG(DISTINCT NULLIF(dq_notes, ''), '; ') AS dq_notes
  FROM `{project}.analytics.stg_budget`
  GROUP BY 1, 2, 3
),
spend AS (
  SELECT
    month_start,
    country,
    engine,
    SUM(spend) AS spend,
    SUM(purchases) AS purchases,
    SUM(revenue) AS revenue,
    COUNT(DISTINCT date) AS days_with_data
  FROM `{project}.analytics.stg_meta`
  GROUP BY 1, 2, 3
)
SELECT
  month_start,
  country,
  engine,
  b.campaign_types,
  b.budget_initial,
  b.budget_current,
  -- niente ROUND: arrotondare riga per riga sposta i totali
  s.spend,
  b.budget_initial - s.spend AS budget_delta,
  SAFE_DIVIDE(s.spend, b.budget_initial) AS budget_used_pct,
  b.forecasted_purchases,
  s.purchases,
  b.forecasted_revenues,
  s.revenue,
  CASE
    WHEN engine != 'Meta' THEN 'Speso non disponibile (engine non integrato)'
    WHEN s.spend IS NULL THEN 'Budget senza speso'
    WHEN b.budget_initial IS NULL THEN 'Speso senza budget'
    WHEN s.spend > b.budget_initial THEN 'Overspending'
    ELSE 'Saving'
  END AS budget_status,
  s.days_with_data,
  EXTRACT(DAY FROM LAST_DAY(month_start)) AS days_in_month,
  COALESCE(s.days_with_data, 0) = EXTRACT(DAY FROM LAST_DAY(month_start)) AS is_month_complete,
  b.dq_notes
FROM budget AS b
FULL OUTER JOIN spend AS s USING (month_start, country, engine)

CREATE OR REPLACE VIEW `{project}.analytics.perf_trend` AS
-- la spina di date rende il periodo precedente quello di calendario anche senza dati
WITH bounds AS (
  SELECT MIN(date) AS first_day, MAX(date) AS last_day FROM `{project}.analytics.stg_meta`
),
countries AS (
  SELECT DISTINCT country FROM `{project}.analytics.stg_meta`
),
spine AS (
  SELECT 'Settimana' AS period_type, period_start, country
  FROM bounds,
    UNNEST(GENERATE_DATE_ARRAY(DATE_TRUNC(first_day, ISOWEEK), last_day, INTERVAL 1 WEEK)) AS period_start,
    countries
  UNION ALL
  SELECT 'Mese', period_start, country
  FROM bounds,
    UNNEST(GENERATE_DATE_ARRAY(DATE_TRUNC(first_day, MONTH), last_day, INTERVAL 1 MONTH)) AS period_start,
    countries
),
actuals AS (
  SELECT 'Settimana' AS period_type, week_start AS period_start, country,
    SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(clicks) AS clicks,
    SUM(purchases) AS purchases, SUM(revenue) AS revenue, COUNT(DISTINCT date) AS days_with_data
  FROM `{project}.analytics.stg_meta`
  GROUP BY 1, 2, 3
  UNION ALL
  SELECT 'Mese', month_start, country,
    SUM(spend), SUM(impressions), SUM(clicks),
    SUM(purchases), SUM(revenue), COUNT(DISTINCT date)
  FROM `{project}.analytics.stg_meta`
  GROUP BY 1, 2, 3
),
filled AS (
  SELECT
    period_type, period_start, country,
    COALESCE(spend, 0) AS spend,
    COALESCE(impressions, 0) AS impressions,
    COALESCE(clicks, 0) AS clicks,
    COALESCE(purchases, 0) AS purchases,
    COALESCE(revenue, 0) AS revenue,
    COALESCE(days_with_data, 0) AS days_with_data
  FROM spine
  LEFT JOIN actuals USING (period_type, period_start, country)
)
SELECT
  *,
  LAG(spend) OVER w AS prev_spend,
  LAG(impressions) OVER w AS prev_impressions,
  LAG(clicks) OVER w AS prev_clicks,
  LAG(purchases) OVER w AS prev_purchases,
  LAG(revenue) OVER w AS prev_revenue,
  LAG(days_with_data) OVER w AS prev_days_with_data
FROM filled
WINDOW w AS (PARTITION BY period_type, country ORDER BY period_start)

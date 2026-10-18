CREATE OR REPLACE VIEW `{project}.analytics.stg_budget` AS
WITH parsed AS (
  SELECT
    snapshot_ts,
    -- lo Sheet non ha l'anno, si assume il 2023 (l'unico presente nei dati Meta)
    DATE(2023, SAFE_CAST(month AS INT64), 1) AS month_start,
    region,
    country,
    channel,
    campaign_type,
    engine AS engine_raw,
    CASE LOWER(TRIM(engine)) WHEN 'gogle' THEN 'Google' ELSE TRIM(engine) END AS engine,
    SAFE_CAST(REGEXP_REPLACE(allocated_budget, r'[^0-9.\-]', '') AS NUMERIC) AS allocated_budget,
    SAFE_CAST(REGEXP_REPLACE(forecasted_imps, r'[^0-9.\-]', '') AS INT64) AS forecasted_impressions,
    SAFE_CAST(REGEXP_REPLACE(forecasted_visits, r'[^0-9.\-]', '') AS INT64) AS forecasted_visits,
    SAFE_CAST(REGEXP_REPLACE(forecasted_purchases, r'[^0-9.\-]', '') AS INT64) AS forecasted_purchases,
    SAFE_CAST(REGEXP_REPLACE(forecasted_revenues, r'[^0-9.\-]', '') AS NUMERIC) AS forecasted_revenues
  FROM `{project}.raw.budget_snapshots`
)
SELECT
  *,
  -- budget iniziale = primo snapshot in cui compare il mese
  snapshot_ts = MIN(snapshot_ts) OVER (PARTITION BY month_start) AS is_initial_version,
  snapshot_ts = MAX(snapshot_ts) OVER (PARTITION BY month_start) AS is_latest_version,
  ARRAY_TO_STRING(ARRAY(
    SELECT note FROM UNNEST([
      IF(LOWER(TRIM(engine_raw)) = 'gogle', 'Engine corretto: Gogle -> Google', NULL),
      IF(engine = 'Meta' AND channel = 'Search', 'Meta associato a una campagna Search', NULL),
      IF(engine = 'Meta' AND country = 'CN', 'Meta non opera in Cina', NULL)
    ]) AS note WHERE note IS NOT NULL
  ), '; ') AS dq_notes
FROM parsed

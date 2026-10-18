CREATE OR REPLACE VIEW `{project}.analytics.data_freshness` AS
SELECT
  source,
  MAX(IF(status = 'success', finished_at, NULL)) AS last_success_at,
  MAX(IF(status = 'success', data_date, NULL)) AS latest_data_date,
  COUNTIF(status = 'failed' AND finished_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)) AS failures_last_7_days
FROM `{project}.ops.pipeline_runs`
GROUP BY source

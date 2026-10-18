CREATE OR REPLACE VIEW `{project}.analytics.perf_by_device` AS
SELECT
  date,
  week_start,
  month_start,
  country,
  platform,
  device_group,
  device,
  SUM(spend) AS spend,
  SUM(impressions) AS impressions,
  SUM(clicks) AS clicks,
  SUM(link_clicks) AS link_clicks,
  SUM(landing_page_views) AS landing_page_views,
  SUM(purchases) AS purchases,
  SUM(revenue) AS revenue
FROM `{project}.analytics.stg_meta`
GROUP BY 1, 2, 3, 4, 5, 6, 7

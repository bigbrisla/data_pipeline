CREATE OR REPLACE VIEW `{project}.analytics.stg_meta` AS
SELECT
  date,
  DATE_TRUNC(date, ISOWEEK) AS week_start,
  DATE_TRUNC(date, MONTH) AS month_start,
  'Meta' AS engine,
  account_name,
  campaign_id,
  REGEXP_REPLACE(campaign_name, r'\x{FFFD}+', "'") AS campaign_name,
  adset_id,
  ad_id,
  objective,
  -- il paese esiste solo nel nome campagna W_<paese>_
  COALESCE(REGEXP_EXTRACT(campaign_name, r'^W_([A-Z]{2})_'), 'N/D') AS country,
  publisher_platform AS platform,
  platform_position,
  impression_device AS device,
  CASE
    WHEN impression_device IN ('iphone', 'android_smartphone', 'ipod') THEN 'Mobile'
    WHEN impression_device IN ('ipad', 'android_tablet') THEN 'Tablet'
    WHEN impression_device = 'desktop' THEN 'Desktop'
    ELSE 'Altro'
  END AS device_group,
  spend,
  impressions,
  reach,
  clicks,
  inline_link_clicks AS link_clicks,
  landing_page_view AS landing_page_views,
  offsite_conversion_fb_pixel_purchase AS purchases,
  offsite_conversion_fb_pixel_purchase_value AS revenue,
  video_view AS video_views
FROM `{project}.raw.meta_insights`

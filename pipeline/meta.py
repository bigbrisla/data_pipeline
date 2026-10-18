import argparse
import csv
import io
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from functools import cache

from google.cloud import bigquery

from pipeline import config, gcp

log = logging.getLogger(__name__)

SOURCE = "meta_insights"
TABLE = f"{config.PROJECT_ID}.{config.RAW_DATASET}.meta_insights"
LOOKBACK_DAYS = 28  # Meta può correggere gli insight fino a 28 giorni dopo

DIMENSIONS = [
    "account_name", "account_id", "campaign_name", "campaign_id", "adset_name", "adset_id",
    "ad_name", "ad_id", "objective", "publisher_platform", "platform_position", "impression_device",
]
METRICS = [
    "spend", "impressions", "reach", "frequency", "clicks", "inline_link_clicks", "inline_post_engagement",
    "outbound_clicks", "post_reaction", "comment", "post", "landing_page_view",
    "offsite_conversion_fb_pixel_purchase", "offsite_conversion_fb_pixel_purchase_value",
    "video_view", "video_p25_watched_actions", "video_p50_watched_actions",
    "video_p75_watched_actions", "video_p100_watched_actions", "video_thruplay_watched_actions",
]
SCHEMA = [
    bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
    *[bigquery.SchemaField(name, "STRING") for name in DIMENSIONS],
    *[bigquery.SchemaField(name, "FLOAT64") for name in METRICS],
    bigquery.SchemaField("_source", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("_loaded_at", "TIMESTAMP", mode="REQUIRED"),
]


class SchemaChangedError(Exception):
    pass


def _to_float(value) -> float | None:
    return None if value in (None, "", "None") else float(value)


class MetaApiSource:
    name = "api"
    API_VERSION = "v25.0"  # versione fissata, aggiornarla è una scelta
    THROTTLING_CODES = {4, 17, 613, 80000, 80003, 80004, 80014}
    API_FIELDS = [
        "account_name", "account_id", "campaign_name", "campaign_id", "adset_name", "adset_id",
        "ad_name", "ad_id", "objective", "spend", "impressions", "reach", "frequency", "clicks",
        "inline_link_clicks", "inline_post_engagement", "outbound_clicks", "actions", "action_values",
        "video_p25_watched_actions", "video_p50_watched_actions", "video_p75_watched_actions",
        "video_p100_watched_actions", "video_thruplay_watched_actions",
    ]
    ACTIONS = {
        "post_reaction": "post_reaction",
        "comment": "comment",
        "post": "post",
        "landing_page_view": "landing_page_view",
        "offsite_conversion_fb_pixel_purchase": "offsite_conversion.fb_pixel_purchase",
        "video_view": "video_view",
    }

    def __init__(self, account_id: str, access_token: str):
        self.url = f"https://graph.facebook.com/{self.API_VERSION}/act_{account_id}/insights"
        self.token = access_token

    def fetch(self, day: date) -> list[dict]:
        params = {
            "access_token": self.token,
            "level": "ad",
            "time_range": json.dumps({"since": day.isoformat(), "until": day.isoformat()}),
            "time_increment": 1,
            "breakdowns": "publisher_platform,platform_position,impression_device",
            "fields": ",".join(self.API_FIELDS),
            "use_unified_attribution_setting": "true",
            "limit": 500,
        }
        rows, url = [], self.url
        while url:
            page = self._get(url, params)
            rows.extend(self._flatten(r, day) for r in page.get("data", []))
            url, params = page.get("paging", {}).get("next"), None
        return rows

    def _get(self, url: str, params: dict | None, max_attempts: int = 6) -> dict:
        for attempt in range(max_attempts):
            body = gcp.http().get(url, params=params, timeout=120).json()
            error = body.get("error")
            if not error:
                return body
            if error.get("code") in self.THROTTLING_CODES:
                wait = 60 * 2 ** attempt
                log.warning("Meta throttling (code %s), retrying in %ss", error.get("code"), wait)
                time.sleep(wait)
                continue
            # 100 e 190 (parametro o token non validi) non si riprovano
            raise RuntimeError(f"Meta API error {error.get('code')}: {error.get('message')}")
        raise RuntimeError("Meta API still throttling after retries")

    def _flatten(self, record: dict, day: date) -> dict:
        def action_sum(items, action_type):
            return sum(float(a["value"]) for a in items or [] if a.get("action_type") == action_type)

        row = {"date": day.isoformat(), **{d: record.get(d) for d in DIMENSIONS}}
        for metric in METRICS:
            value = record.get(metric)
            row[metric] = action_sum(value, "video_view" if "video" in metric else "outbound_click") \
                if isinstance(value, list) else _to_float(value)
        for column, action_type in self.ACTIONS.items():
            row[column] = action_sum(record.get("actions"), action_type)
        row["offsite_conversion_fb_pixel_purchase_value"] = action_sum(
            record.get("action_values"), "offsite_conversion.fb_pixel_purchase")
        return row


class MockMetaSource:
    name = "mock"

    @cache
    def _all_rows(self) -> dict[str, list[dict]]:
        url = config.sheet_csv_url(config.META_MOCK_SHEET_ID, config.META_MOCK_SHEET_GID)
        response = gcp.http().get(url, timeout=60)
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.content.decode("utf-8")))
        missing = set(DIMENSIONS + METRICS + ["date"]) - set(reader.fieldnames or [])
        if missing:
            raise SchemaChangedError(f"Columns missing from source: {sorted(missing)}")
        by_day: dict[str, list[dict]] = {}
        for r in reader:
            row = {"date": r["date"], **{d: r[d] for d in DIMENSIONS}, **{m: _to_float(r[m]) for m in METRICS}}
            by_day.setdefault(r["date"], []).append(row)
        return by_day

    def fetch(self, day: date) -> list[dict]:
        return self._all_rows().get(day.isoformat(), [])


def get_source():
    if os.getenv("META_SOURCE", "mock") == "api":
        return MetaApiSource(os.environ["META_AD_ACCOUNT_ID"], os.environ["META_ACCESS_TOKEN"])
    return MockMetaSource()


def load_day(source, day: date) -> dict:
    rows = source.fetch(day)
    if not rows:
        # un risultato vuoto non cancella mai una partizione già caricata
        log.warning("%s: no rows returned, existing partition left untouched", day)
        return gcp.run_record(SOURCE, "empty", data_date=day, detail=f"source={source.name}")

    now = datetime.now(timezone.utc)
    for row in rows:
        row.update(_source=source.name, _loaded_at=now.isoformat())
    payload = "\n".join(json.dumps(r) for r in rows).encode()
    gcp.upload_raw(payload, f"meta/insights/date={day}/{now:%Y%m%dT%H%M%S}.jsonl", "application/x-ndjson")

    loaded = gcp.load_rows(rows, TABLE, SCHEMA, bigquery.WriteDisposition.WRITE_TRUNCATE, partition=day)
    log.info("%s: %d rows loaded", day, loaded)
    return gcp.run_record(SOURCE, "success", rows_loaded=loaded, data_date=day, detail=f"source={source.name}")


def run(start: date, end: date) -> bool:
    source = get_source()
    records, failed = [], []
    day = start
    try:
        while day <= end:
            try:
                records.append(load_day(source, day))
            except Exception as exc:
                log.exception("%s: failed", day)
                records.append(gcp.run_record(SOURCE, "failed", data_date=day, detail=f"{type(exc).__name__}: {exc}"))
                failed.append(day)
            day += timedelta(days=1)
    finally:
        gcp.write_run_log(records)
    if failed:
        log.error("Failed days (re-run them with --date): %s", ", ".join(map(str, failed)))
    return not failed


def parse_args() -> tuple[date, date]:
    parser = argparse.ArgumentParser(description="Load Meta insights into BigQuery")
    parser.add_argument("--date", type=date.fromisoformat, help="single day (YYYY-MM-DD)")
    parser.add_argument("--start", type=date.fromisoformat, help="first day of a range")
    parser.add_argument("--end", type=date.fromisoformat, help="last day of a range")
    args = parser.parse_args()
    if args.date:
        return args.date, args.date
    if args.start or args.end:
        if not (args.start and args.end) or args.start > args.end:
            parser.error("--start and --end must be given together, with start <= end")
        return args.start, args.end
    yesterday = date.today() - timedelta(days=1)
    return yesterday - timedelta(days=LOOKBACK_DAYS - 1), yesterday


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    start, end = parse_args()
    sys.exit(0 if run(start, end) else 1)

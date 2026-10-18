import argparse
import csv
import hashlib
import io
import logging
from datetime import datetime, timezone

from google.cloud import bigquery

from pipeline import config, gcp

log = logging.getLogger(__name__)

SOURCE = "google_sheets_budget"
TABLE = f"{config.PROJECT_ID}.{config.RAW_DATASET}.budget_snapshots"

# se un'intestazione cambia il job fallisce, non carica dati sbagliati
COLUMNS = {
    "Month": "month",
    "Region": "region",
    "Country": "country",
    "Channel": "channel",
    "Campaign Type": "campaign_type",
    "Engine": "engine",
    "Allocated Budget": "allocated_budget",
    "Forecasted Imps": "forecasted_imps",
    "Forecasted Visits": "forecasted_visits",
    "Forecasted Purchases": "forecasted_purchases",
    "Forecasted Revenues": "forecasted_revenues",
}

SCHEMA = [
    bigquery.SchemaField("snapshot_ts", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("content_hash", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("row_number", "INT64", mode="REQUIRED"),
    *[bigquery.SchemaField(name, "STRING") for name in COLUMNS.values()],
]


class SchemaChangedError(Exception):
    pass


def fetch() -> bytes:
    url = config.sheet_csv_url(config.BUDGET_SHEET_ID, config.BUDGET_SHEET_GID)
    response = gcp.http().get(url, timeout=30)
    response.raise_for_status()
    return response.content


def parse(content: bytes) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    header = [h.strip() for h in reader.fieldnames or []]
    missing = set(COLUMNS) - set(header)
    if missing:
        raise SchemaChangedError(f"Sheet columns missing or renamed: {sorted(missing)}")
    unexpected = set(header) - set(COLUMNS)
    if unexpected:
        log.warning("New columns ignored, update the contract if needed: %s", sorted(unexpected))

    rows = []
    for row in reader:
        values = {COLUMNS[k.strip()]: (v or "").strip() for k, v in row.items() if k and k.strip() in COLUMNS}
        if any(values.values()):
            rows.append(values)
    return rows


def latest_hash() -> str | None:
    query = f"SELECT content_hash FROM `{TABLE}` ORDER BY snapshot_ts DESC LIMIT 1"
    result = list(gcp.bq().query(query).result())
    return result[0].content_hash if result else None


def run(force: bool = False) -> None:
    try:
        content = fetch()
        content_hash = hashlib.sha256(content).hexdigest()

        if not force and content_hash == latest_hash():
            log.info("Sheet unchanged since last snapshot, nothing to load")
            gcp.log_run(SOURCE, "skipped", detail="content unchanged")
            return

        rows = parse(content)
        if not rows:
            # uno Sheet vuoto è quasi sempre un errore di modifica, si tiene l'ultimo snapshot buono
            raise ValueError("Sheet is empty, refusing to load an empty snapshot")

        now = datetime.now(timezone.utc)
        gcp.upload_raw(content, f"sheets/budget/{now:%Y/%m/%d}/{now:%H%M%S}_{content_hash[:8]}.csv", "text/csv")

        snapshot = [
            {"snapshot_ts": now.isoformat(), "content_hash": content_hash, "row_number": i, **row}
            for i, row in enumerate(rows, start=1)
        ]
        loaded = gcp.load_rows(snapshot, TABLE, SCHEMA, bigquery.WriteDisposition.WRITE_APPEND)
        log.info("Loaded new budget snapshot: %d rows", loaded)
        gcp.log_run(SOURCE, "success", rows_loaded=loaded, detail=f"hash {content_hash[:8]}")
    except Exception as exc:
        gcp.log_run(SOURCE, "failed", detail=f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Load the budget Google Sheet into BigQuery")
    parser.add_argument("--force", action="store_true", help="load a snapshot even if the content is unchanged")
    run(force=parser.parse_args().force)

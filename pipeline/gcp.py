import json
import logging
import uuid
from datetime import date, datetime, timezone
from functools import cache

import requests
from google.cloud import bigquery, storage
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pipeline import config

log = logging.getLogger(__name__)

RUNS_TABLE = f"{config.PROJECT_ID}.{config.OPS_DATASET}.pipeline_runs"
RUNS_SCHEMA = [
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("source", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("data_date", "DATE"),
    bigquery.SchemaField("status", "STRING", mode="REQUIRED"),  # success, skipped, empty o failed
    bigquery.SchemaField("rows_loaded", "INT64"),
    bigquery.SchemaField("detail", "STRING"),
    bigquery.SchemaField("finished_at", "TIMESTAMP", mode="REQUIRED"),
]


@cache
def bq() -> bigquery.Client:
    return bigquery.Client(project=config.PROJECT_ID, location=config.LOCATION)


@cache
def gcs() -> storage.Client:
    return storage.Client(project=config.PROJECT_ID)


@cache
def http() -> requests.Session:
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def upload_raw(content: bytes, path: str, content_type: str) -> str:
    blob = gcs().bucket(config.BUCKET).blob(path)
    blob.upload_from_string(content, content_type=content_type)
    uri = f"gs://{config.BUCKET}/{path}"
    log.info("Raw payload saved to %s", uri)
    return uri


def load_rows(rows: list[dict], table: str, schema: list[bigquery.SchemaField],
              write_disposition: str, partition: date | None = None) -> int:
    # con WRITE_TRUNCATE su una partizione si sostituisce solo quel giorno, rilanciare la stessa data non duplica
    destination = f"{table}${partition:%Y%m%d}" if partition else table
    job_config = bigquery.LoadJobConfig(schema=schema, write_disposition=write_disposition)
    job = bq().load_table_from_json(rows, destination, job_config=job_config)
    job.result()
    return job.output_rows or 0


def run_record(source: str, status: str, rows_loaded: int = 0, detail: str = "",
               data_date: date | None = None) -> dict:
    row = {
        "run_id": str(uuid.uuid4()),
        "source": source,
        "data_date": data_date.isoformat() if data_date else None,
        "status": status,
        "rows_loaded": rows_loaded,
        "detail": detail[:1000],
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    log.info("Run log: %s", json.dumps(row))
    return row


def write_run_log(records: list[dict]) -> None:
    if records:
        load_rows(records, RUNS_TABLE, RUNS_SCHEMA, bigquery.WriteDisposition.WRITE_APPEND)


def log_run(source: str, status: str, **kwargs) -> None:
    write_run_log([run_record(source, status, **kwargs)])

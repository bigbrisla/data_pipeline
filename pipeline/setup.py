import logging

from google.api_core.exceptions import Conflict
from google.cloud import bigquery

from pipeline import config, gcp, meta, sheets

log = logging.getLogger(__name__)


def create_bucket() -> None:
    try:
        gcp.gcs().create_bucket(config.BUCKET, location=config.LOCATION)
        log.info("Created bucket gs://%s", config.BUCKET)
    except Conflict:
        log.info("Bucket gs://%s already exists", config.BUCKET)


def create_datasets() -> None:
    for name in (config.RAW_DATASET, config.ANALYTICS_DATASET, config.OPS_DATASET):
        dataset = bigquery.Dataset(f"{config.PROJECT_ID}.{name}")
        dataset.location = config.LOCATION
        gcp.bq().create_dataset(dataset, exists_ok=True)
        log.info("Dataset %s ready", name)


def create_table(table_id: str, schema: list[bigquery.SchemaField], partition_field: str) -> None:
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(field=partition_field)
    gcp.bq().create_table(table, exists_ok=True)
    log.info("Table %s ready", table_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    create_bucket()
    create_datasets()
    create_table(gcp.RUNS_TABLE, gcp.RUNS_SCHEMA, "finished_at")
    create_table(sheets.TABLE, sheets.SCHEMA, "snapshot_ts")
    create_table(meta.TABLE, meta.SCHEMA, "date")

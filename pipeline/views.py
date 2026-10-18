import logging

from pipeline import config, gcp

log = logging.getLogger(__name__)

SQL_DIR = config.ROOT / "sql"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for path in sorted(SQL_DIR.glob("*.sql")):
        gcp.bq().query(path.read_text().replace("{project}", config.PROJECT_ID)).result()
        log.info("Applied %s", path.name)

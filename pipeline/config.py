import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required setting {name} (see .env.example)")
    return value


PROJECT_ID = _required("GCP_PROJECT")
LOCATION = os.getenv("GCP_LOCATION", "EU")
BUCKET = _required("GCS_BUCKET")

RAW_DATASET = "raw"
ANALYTICS_DATASET = "analytics"
OPS_DATASET = "ops"

BUDGET_SHEET_ID = _required("BUDGET_SHEET_ID")
BUDGET_SHEET_GID = os.getenv("BUDGET_SHEET_GID", "0")
META_MOCK_SHEET_ID = _required("META_MOCK_SHEET_ID")
META_MOCK_SHEET_GID = _required("META_MOCK_SHEET_GID")


def sheet_csv_url(sheet_id: str, gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

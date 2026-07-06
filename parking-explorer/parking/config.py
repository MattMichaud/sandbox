"""Environment-driven configuration.

Everything is overridable via a local .env file (see .env.example) so the same
code runs against the real table or a scratch copy without edits.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
TABLE_NAME = os.getenv("PARKING_TABLE_NAME", "franklin_parking_api_data")
LOCAL_TZ = os.getenv("PARKING_TZ", "America/Chicago")

DB_PATH = Path(os.getenv("PARKING_DB_PATH", PROJECT_ROOT / "parking.duckdb"))

# Ignore data before this local date. The Lambda had a ~6-month outage in 2025;
# continuous collection resumed 2025-08-20, so earlier data is dropped on sync
# and never re-downloaded. Set PARKING_START_DATE="" to keep everything.
_start = os.getenv("PARKING_START_DATE", "2025-08-20").strip()
START_DATE = dt.date.fromisoformat(_start) if _start else None

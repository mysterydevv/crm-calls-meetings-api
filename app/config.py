import os
from datetime import time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / "schema.sql"
DEFAULT_DB_PATH = BASE_DIR / "crm.db"

BUSINESS_TZ = ZoneInfo("Asia/Almaty")
MEETING_DURATION = timedelta(minutes=60)
WORK_START = time(9, 0)
WORK_END = time(18, 0)

SEED_MANAGERS = (
    "Айгуль Нурланова",
    "Тимур Касымов",
    "Дамир Сериков",
)


def get_db_path() -> str:
    return os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH))

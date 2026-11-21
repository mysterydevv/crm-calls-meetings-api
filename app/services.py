from datetime import datetime, timezone

from app.schemas import format_utc


def utc_now_iso() -> str:
    return format_utc(datetime.now(timezone.utc).replace(microsecond=0))


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt.astimezone(timezone.utc)

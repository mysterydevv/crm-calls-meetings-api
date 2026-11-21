import sqlite3
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException, status

from app.config import BUSINESS_TZ, MEETING_DURATION, WORK_END, WORK_START
from app.schemas import MeetingResponse, format_utc


def utc_now_iso() -> str:
    return format_utc(datetime.now(timezone.utc).replace(microsecond=0))


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt.astimezone(timezone.utc)


def intervals_overlap(
    start1: datetime,
    end1: datetime,
    start2: datetime,
    end2: datetime,
) -> bool:
    """Half-open interval overlap: [start1, end1) intersects [start2, end2)."""
    return start1 < end2 and start2 < end1


def validate_working_hours(scheduled_at_utc: datetime) -> None:
    local_start = scheduled_at_utc.astimezone(BUSINESS_TZ)
    local_end = local_start + MEETING_DURATION

    if local_start.weekday() >= 5:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Meetings can only be scheduled on weekdays (Monday-Friday) "
                "in Asia/Almaty timezone."
            ),
        )

    work_start_dt = datetime.combine(local_start.date(), WORK_START, tzinfo=BUSINESS_TZ)
    work_end_dt = datetime.combine(local_start.date(), WORK_END, tzinfo=BUSINESS_TZ)

    if local_start < work_start_dt or local_end > work_end_dt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Meeting (60 minutes) must fit entirely within working hours "
                "09:00-18:00 Asia/Almaty (latest start time is 17:00 Asia/Almaty)."
            ),
        )


def check_scheduling_conflicts(
    db: sqlite3.Connection,
    manager_id: int,
    company_id: int,
    scheduled_at_utc: datetime,
    exclude_meeting_id: int | None = None,
) -> None:
    new_start = scheduled_at_utc.astimezone(timezone.utc)
    new_end = new_start + MEETING_DURATION

    manager_rows = db.execute(
        """
        SELECT id, scheduled_at
        FROM meetings
        WHERE manager_id = ? AND status = 'scheduled'
        """,
        (manager_id,),
    ).fetchall()

    for row in manager_rows:
        if exclude_meeting_id is not None and row["id"] == exclude_meeting_id:
            continue
        existing_start = parse_utc(row["scheduled_at"])
        existing_end = existing_start + MEETING_DURATION
        if intervals_overlap(new_start, new_end, existing_start, existing_end):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Manager {manager_id} already has an overlapping meeting "
                    f"(id={row['id']}) at {row['scheduled_at']}."
                ),
            )

    company_rows = db.execute(
        """
        SELECT id, manager_id, scheduled_at
        FROM meetings
        WHERE company_id = ? AND status = 'scheduled'
        """,
        (company_id,),
    ).fetchall()

    for row in company_rows:
        if exclude_meeting_id is not None and row["id"] == exclude_meeting_id:
            continue
        existing_start = parse_utc(row["scheduled_at"])
        existing_end = existing_start + MEETING_DURATION
        if intervals_overlap(new_start, new_end, existing_start, existing_end):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Company {company_id} already has an overlapping active meeting "
                    f"(id={row['id']}, manager_id={row['manager_id']}) at {row['scheduled_at']}."
                ),
            )


def almaty_day_bounds_utc(target_date: date) -> tuple[datetime, datetime]:
    day_start_local = datetime.combine(target_date, time(0, 0), tzinfo=BUSINESS_TZ)
    day_end_local = day_start_local + timedelta(days=1)
    return day_start_local.astimezone(timezone.utc), day_end_local.astimezone(timezone.utc)


def row_to_meeting_response(row: sqlite3.Row) -> MeetingResponse:
    start_dt = parse_utc(row["scheduled_at"])
    ends_at = format_utc(start_dt + MEETING_DURATION)
    return MeetingResponse(
        id=row["id"],
        company_id=row["company_id"],
        manager_id=row["manager_id"],
        scheduled_at=row["scheduled_at"],
        ends_at=ends_at,
        original_scheduled_at=row["original_scheduled_at"],
        reschedule_count=row["reschedule_count"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

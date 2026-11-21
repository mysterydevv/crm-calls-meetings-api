import sqlite3
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, status

from app.config import MEETING_DURATION
from app.database import get_db, init_db
from app.schemas import (
    CompanyCreate,
    CompanyListResponse,
    CompanyResponse,
    CompanyStatus,
    ManagerResponse,
    ManagerScheduleResponse,
    MeetingCreate,
    MeetingResponse,
    ScheduleMeetingItem,
    format_utc,
)
from app.services import (
    almaty_day_bounds_utc,
    check_scheduling_conflicts,
    parse_utc,
    row_to_meeting_response,
    utc_now_iso,
    validate_working_hours,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Internal CRM API",
    description="REST API для учёта звонков и назначения встреч.",
    version="1.0.0",
    lifespan=lifespan,
)


def _get_company_or_404(db: sqlite3.Connection, company_id: int) -> sqlite3.Row:
    row = db.execute(
        "SELECT id, name, bin, phone, status, created_at FROM companies WHERE id = ?",
        (company_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with id={company_id} not found.",
        )
    return row


def _get_manager_or_404(db: sqlite3.Connection, manager_id: int) -> sqlite3.Row:
    row = db.execute(
        "SELECT id, name FROM managers WHERE id = ?",
        (manager_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Manager with id={manager_id} not found.",
        )
    return row


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/managers", response_model=list[ManagerResponse])
def list_managers(db: sqlite3.Connection = Depends(get_db)) -> list[ManagerResponse]:
    rows = db.execute("SELECT id, name FROM managers ORDER BY id ASC").fetchall()
    return [ManagerResponse(**dict(row)) for row in rows]


@app.get("/managers/{manager_id}/schedule", response_model=ManagerScheduleResponse)
def get_manager_schedule(
    manager_id: int,
    schedule_date: date = Query(..., alias="date", description="Calendar date in Asia/Almaty (YYYY-MM-DD)"),
    db: sqlite3.Connection = Depends(get_db),
) -> ManagerScheduleResponse:
    manager_row = _get_manager_or_404(db, manager_id)
    day_start_utc, day_end_utc = almaty_day_bounds_utc(schedule_date)

    rows = db.execute(
        """
        SELECT
            m.id AS meeting_id,
            m.scheduled_at,
            m.original_scheduled_at,
            m.reschedule_count,
            m.status AS meeting_status,
            c.id AS company_id,
            c.name AS company_name,
            c.bin AS company_bin,
            c.phone AS company_phone,
            c.status AS company_status,
            c.created_at AS company_created_at
        FROM meetings m
        JOIN companies c ON c.id = m.company_id
        WHERE m.manager_id = ? AND m.status = 'scheduled'
        ORDER BY m.scheduled_at ASC
        """,
        (manager_id,),
    ).fetchall()

    items: list[ScheduleMeetingItem] = []
    for row in rows:
        start_dt = parse_utc(row["scheduled_at"])
        if day_start_utc <= start_dt < day_end_utc:
            items.append(
                ScheduleMeetingItem(
                    id=row["meeting_id"],
                    scheduled_at=row["scheduled_at"],
                    ends_at=format_utc(start_dt + MEETING_DURATION),
                    original_scheduled_at=row["original_scheduled_at"],
                    reschedule_count=row["reschedule_count"],
                    status=row["meeting_status"],
                    company=CompanyResponse(
                        id=row["company_id"],
                        name=row["company_name"],
                        bin=row["company_bin"],
                        phone=row["company_phone"],
                        status=row["company_status"],
                        created_at=row["company_created_at"],
                    ),
                )
            )

    items.sort(key=lambda item: parse_utc(item.scheduled_at))

    return ManagerScheduleResponse(
        manager=ManagerResponse(**dict(manager_row)),
        date=schedule_date.isoformat(),
        timezone="Asia/Almaty",
        meetings=items,
    )


@app.post(
    "/companies",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_company(
    payload: CompanyCreate,
    db: sqlite3.Connection = Depends(get_db),
) -> CompanyResponse:
    now = utc_now_iso()
    try:
        cursor = db.execute(
            """
            INSERT INTO companies (name, bin, phone, status, created_at)
            VALUES (?, ?, ?, 'new', ?)
            """,
            (payload.name, payload.bin, payload.phone, now),
        )
        db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Company with BIN '{payload.bin}' already exists.",
        )

    row = _get_company_or_404(db, cursor.lastrowid)
    return CompanyResponse(**dict(row))


@app.get("/companies", response_model=CompanyListResponse)
def list_companies(
    company_status: CompanyStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
) -> CompanyListResponse:
    where_clause = ""
    params: list[object] = []

    if company_status is not None:
        where_clause = "WHERE status = ?"
        params.append(company_status)

    total = db.execute(
        f"SELECT COUNT(*) FROM companies {where_clause}",
        params,
    ).fetchone()[0]

    rows = db.execute(
        f"""
        SELECT id, name, bin, phone, status, created_at
        FROM companies
        {where_clause}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()

    return CompanyListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[CompanyResponse(**dict(row)) for row in rows],
    )


@app.post(
    "/meetings",
    response_model=MeetingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_meeting(
    payload: MeetingCreate,
    db: sqlite3.Connection = Depends(get_db),
) -> MeetingResponse:
    _get_company_or_404(db, payload.company_id)
    _get_manager_or_404(db, payload.manager_id)

    validate_working_hours(payload.scheduled_at)
    check_scheduling_conflicts(
        db=db,
        manager_id=payload.manager_id,
        company_id=payload.company_id,
        scheduled_at_utc=payload.scheduled_at,
    )

    scheduled_iso = format_utc(payload.scheduled_at)
    now = utc_now_iso()

    cursor = db.execute(
        """
        INSERT INTO meetings (
            company_id,
            manager_id,
            scheduled_at,
            original_scheduled_at,
            reschedule_count,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, 0, 'scheduled', ?, ?)
        """,
        (
            payload.company_id,
            payload.manager_id,
            scheduled_iso,
            scheduled_iso,
            now,
            now,
        ),
    )
    db.commit()

    row = db.execute(
        """
        SELECT id, company_id, manager_id, scheduled_at, original_scheduled_at,
               reschedule_count, status, created_at, updated_at
        FROM meetings
        WHERE id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    return row_to_meeting_response(row)

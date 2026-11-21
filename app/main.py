import sqlite3
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status

from app.database import get_db, init_db
from app.schemas import (
    CompanyCreate,
    CompanyListResponse,
    CompanyResponse,
    CompanyStatus,
    ManagerResponse,
)
from app.services import utc_now_iso


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


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/managers", response_model=list[ManagerResponse])
def list_managers(db: sqlite3.Connection = Depends(get_db)) -> list[ManagerResponse]:
    rows = db.execute("SELECT id, name FROM managers ORDER BY id ASC").fetchall()
    return [ManagerResponse(**dict(row)) for row in rows]


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

    row = db.execute(
        "SELECT id, name, bin, phone, status, created_at FROM companies WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()
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

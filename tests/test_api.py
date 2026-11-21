import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    db_file = tmp_path / "test_crm.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    init_db(str(db_file))

    with TestClient(app) as test_client:
        yield test_client


def _create_company(
    client: TestClient,
    name: str = "ТОО Алматы Трейд",
    bin_code: str = "170340021554",
    phone: str = "+77011234567",
) -> dict:
    resp = client.post(
        "/companies",
        json={"name": name, "bin": bin_code, "phone": phone},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_companies_create_duplicate_bin_and_pagination(client: TestClient) -> None:
    c1 = _create_company(client, "ТОО Альфа", "111111111111", "+77010000001")
    c2 = _create_company(client, "ТОО Бета", "222222222222", "+77010000002")
    _create_company(client, "ТОО Гамма", "333333333333", "+77010000003")

    # Duplicate BIN must return 409 Conflict
    dup = client.post(
        "/companies",
        json={"name": "ТОО Дубль", "bin": "111111111111", "phone": "+77019999999"},
    )
    assert dup.status_code == 409
    assert "already exists" in dup.json()["detail"]

    # Invalid BIN (not 12 digits) must return 422
    bad_bin = client.post(
        "/companies",
        json={"name": "ТОО Ошибка", "bin": "12345", "phone": "+77019999999"},
    )
    assert bad_bin.status_code == 422

    # Update c1 status via call so we can test status filter
    call_resp = client.post(
        "/calls",
        json={"company_id": c1["id"], "manager_id": 1, "result": "no_answer"},
    )
    assert call_resp.status_code == 201

    # Filter by status=no_answer
    filtered = client.get("/companies", params={"status": "no_answer"})
    assert filtered.status_code == 200
    data = filtered.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == c1["id"]

    # Pagination
    page = client.get("/companies", params={"limit": 2, "offset": 1})
    assert page.status_code == 200
    page_data = page.json()
    assert page_data["total"] == 3
    assert len(page_data["items"]) == 2
    assert c2["id"] in [item["id"] for item in page_data["items"]]


def test_manager_overlap_rejected_and_back_to_back_allowed(client: TestClient) -> None:
    c1 = _create_company(client, "ТОО Один", "100000000001")
    c2 = _create_company(client, "ТОО Два", "100000000002")
    c3 = _create_company(client, "ТОО Три", "100000000003")

    # Monday 2026-11-23 10:00-11:00 Asia/Almaty = 05:00-06:00 UTC
    m1 = client.post(
        "/meetings",
        json={"company_id": c1["id"], "manager_id": 1, "scheduled_at": "2026-11-23T05:00:00Z"},
    )
    assert m1.status_code == 201

    # Overlapping slot for same manager: 10:30-11:30 Asia/Almaty = 05:30 UTC -> 409
    overlap = client.post(
        "/meetings",
        json={"company_id": c2["id"], "manager_id": 1, "scheduled_at": "2026-11-23T05:30:00Z"},
    )
    assert overlap.status_code == 409
    assert "overlapping meeting" in overlap.json()["detail"]

    # Back-to-back slot for same manager: 11:00-12:00 Asia/Almaty = 06:00 UTC -> 201
    adjacent = client.post(
        "/meetings",
        json={"company_id": c3["id"], "manager_id": 1, "scheduled_at": "2026-11-23T06:00:00Z"},
    )
    assert adjacent.status_code == 201
    assert adjacent.json()["scheduled_at"] == "2026-11-23T06:00:00Z"
    assert adjacent.json()["ends_at"] == "2026-11-23T07:00:00Z"


def test_company_overlap_with_different_managers_rejected(client: TestClient) -> None:
    c1 = _create_company(client, "ТОО Клиент", "200000000001")

    # Manager 1 books 10:00-11:00 Asia/Almaty (05:00 UTC)
    first = client.post(
        "/meetings",
        json={"company_id": c1["id"], "manager_id": 1, "scheduled_at": "2026-11-23T05:00:00Z"},
    )
    assert first.status_code == 201

    # Manager 2 tries to book same company at 10:45-11:45 Asia/Almaty (05:45 UTC) -> 409
    second = client.post(
        "/meetings",
        json={"company_id": c1["id"], "manager_id": 2, "scheduled_at": "2026-11-23T05:45:00Z"},
    )
    assert second.status_code == 409
    assert "already has an overlapping active meeting" in second.json()["detail"]


def test_working_hours_boundaries_and_timezone_validation(client: TestClient) -> None:
    c1 = _create_company(client, "ТОО Границы 1", "300000000001")
    c2 = _create_company(client, "ТОО Границы 2", "300000000002")

    # 09:00 Asia/Almaty = 04:00 UTC (Monday) -> allowed
    at_0900 = client.post(
        "/meetings",
        json={"company_id": c1["id"], "manager_id": 1, "scheduled_at": "2026-11-23T04:00:00Z"},
    )
    assert at_0900.status_code == 201

    # 08:59 Asia/Almaty = 03:59 UTC -> rejected
    at_0859 = client.post(
        "/meetings",
        json={"company_id": c2["id"], "manager_id": 2, "scheduled_at": "2026-11-23T03:59:00Z"},
    )
    assert at_0859.status_code == 422

    # 17:00 Asia/Almaty = 12:00 UTC (ends 18:00 Asia/Almaty) -> allowed
    at_1700 = client.post(
        "/meetings",
        json={"company_id": c1["id"], "manager_id": 1, "scheduled_at": "2026-11-23T12:00:00Z"},
    )
    assert at_1700.status_code == 201

    # 17:01 Asia/Almaty = 12:01 UTC (ends 18:01 Asia/Almaty) -> rejected
    at_1701 = client.post(
        "/meetings",
        json={"company_id": c2["id"], "manager_id": 2, "scheduled_at": "2026-11-23T12:01:00Z"},
    )
    assert at_1701.status_code == 422

    # 17:30 Asia/Almaty = 12:30 UTC -> rejected
    at_1730 = client.post(
        "/meetings",
        json={"company_id": c2["id"], "manager_id": 2, "scheduled_at": "2026-11-23T12:30:00Z"},
    )
    assert at_1730.status_code == 422

    # Saturday 2026-11-21 10:00 Asia/Almaty = 05:00 UTC -> rejected
    saturday = client.post(
        "/meetings",
        json={"company_id": c2["id"], "manager_id": 2, "scheduled_at": "2026-11-21T05:00:00Z"},
    )
    assert saturday.status_code == 422
    assert "weekdays" in saturday.json()["detail"]

    # Naive datetime without timezone -> rejected with 422
    naive = client.post(
        "/meetings",
        json={"company_id": c2["id"], "manager_id": 2, "scheduled_at": "2026-11-23T06:00:00"},
    )
    assert naive.status_code == 422


def test_call_meeting_set_requires_valid_active_meeting(client: TestClient) -> None:
    c1 = _create_company(client, "ТОО Звонок 1", "400000000001")
    c2 = _create_company(client, "ТОО Звонок 2", "400000000002")

    # 1. meeting_set without meeting_id -> 422
    no_meeting = client.post(
        "/calls",
        json={"company_id": c1["id"], "manager_id": 1, "result": "meeting_set"},
    )
    assert no_meeting.status_code == 422

    # 2. meeting_set with non-existent meeting_id -> 422
    missing_meeting = client.post(
        "/calls",
        json={
            "company_id": c1["id"],
            "manager_id": 1,
            "result": "meeting_set",
            "meeting_id": 9999,
        },
    )
    assert missing_meeting.status_code == 422

    # 3. meeting_set with another company's meeting -> 422
    other_meeting = client.post(
        "/meetings",
        json={"company_id": c2["id"], "manager_id": 1, "scheduled_at": "2026-11-23T05:00:00Z"},
    ).json()
    wrong_company = client.post(
        "/calls",
        json={
            "company_id": c1["id"],
            "manager_id": 1,
            "result": "meeting_set",
            "meeting_id": other_meeting["id"],
        },
    )
    assert wrong_company.status_code == 422

    # 4. Valid active meeting for c1 -> 201 and company status becomes 'meeting_set'
    c1_meeting = client.post(
        "/meetings",
        json={"company_id": c1["id"], "manager_id": 2, "scheduled_at": "2026-11-23T05:00:00Z"},
    ).json()
    valid_call = client.post(
        "/calls",
        json={
            "company_id": c1["id"],
            "manager_id": 2,
            "result": "meeting_set",
            "meeting_id": c1_meeting["id"],
            "notes": "Договорились о встрече в офисе",
        },
    )
    assert valid_call.status_code == 201
    assert valid_call.json()["meeting_id"] == c1_meeting["id"]

    companies = client.get("/companies", params={"status": "meeting_set"}).json()
    assert companies["total"] == 1
    assert companies["items"][0]["id"] == c1["id"]


def test_reschedule_preserves_original_time_and_increments_counter(client: TestClient) -> None:
    c1 = _create_company(client, "ТОО Перенос", "500000000001")

    created = client.post(
        "/meetings",
        json={"company_id": c1["id"], "manager_id": 1, "scheduled_at": "2026-11-23T05:00:00Z"},
    )
    assert created.status_code == 201
    meeting = created.json()
    assert meeting["original_scheduled_at"] == "2026-11-23T05:00:00Z"
    assert meeting["reschedule_count"] == 0

    # Shift by 30 minutes (overlaps with its own old slot -> must be allowed!)
    rescheduled = client.patch(
        f"/meetings/{meeting['id']}",
        json={"scheduled_at": "2026-11-23T05:30:00Z"},
    )
    assert rescheduled.status_code == 200
    updated = rescheduled.json()
    assert updated["scheduled_at"] == "2026-11-23T05:30:00Z"
    assert updated["original_scheduled_at"] == "2026-11-23T05:00:00Z"
    assert updated["reschedule_count"] == 1

    # Reschedule again to 14:00 Asia/Almaty (09:00 UTC)
    rescheduled_2 = client.patch(
        f"/meetings/{meeting['id']}",
        json={"scheduled_at": "2026-11-23T09:00:00Z"},
    )
    assert rescheduled_2.status_code == 200
    updated_2 = rescheduled_2.json()
    assert updated_2["scheduled_at"] == "2026-11-23T09:00:00Z"
    assert updated_2["original_scheduled_at"] == "2026-11-23T05:00:00Z"
    assert updated_2["reschedule_count"] == 2


def test_cancel_meeting_frees_slot_and_blocks_meeting_set_call(client: TestClient) -> None:
    c1 = _create_company(client, "ТОО Отмена 1", "600000000001")
    c2 = _create_company(client, "ТОО Отмена 2", "600000000002")

    m1 = client.post(
        "/meetings",
        json={"company_id": c1["id"], "manager_id": 1, "scheduled_at": "2026-11-23T05:00:00Z"},
    ).json()

    cancelled = client.patch(
        f"/meetings/{m1['id']}",
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    # Cancelled meeting cannot be linked in POST /calls with result=meeting_set
    bad_call = client.post(
        "/calls",
        json={
            "company_id": c1["id"],
            "manager_id": 1,
            "result": "meeting_set",
            "meeting_id": m1["id"],
        },
    )
    assert bad_call.status_code == 422

    # Slot is now free for another company with the same manager
    m2 = client.post(
        "/meetings",
        json={"company_id": c2["id"], "manager_id": 1, "scheduled_at": "2026-11-23T05:00:00Z"},
    )
    assert m2.status_code == 201


def test_manager_schedule_filters_by_almaty_date_and_returns_utc(client: TestClient) -> None:
    c1 = _create_company(client, "ТОО Утро", "700000000001")
    c2 = _create_company(client, "ТОО Вечер", "700000000002")
    c3 = _create_company(client, "ТОО Завтра", "700000000003")

    # 2026-11-23 09:00 Asia/Almaty = 04:00 UTC
    client.post(
        "/meetings",
        json={"company_id": c1["id"], "manager_id": 1, "scheduled_at": "2026-11-23T04:00:00Z"},
    )
    # 2026-11-23 17:00 Asia/Almaty = 12:00 UTC
    client.post(
        "/meetings",
        json={"company_id": c2["id"], "manager_id": 1, "scheduled_at": "2026-11-23T12:00:00Z"},
    )
    # 2026-11-24 10:00 Asia/Almaty = 05:00 UTC (next day)
    client.post(
        "/meetings",
        json={"company_id": c3["id"], "manager_id": 1, "scheduled_at": "2026-11-24T05:00:00Z"},
    )

    resp = client.get("/managers/1/schedule", params={"date": "2026-11-23"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["manager"]["id"] == 1
    assert body["date"] == "2026-11-23"
    assert body["timezone"] == "Asia/Almaty"
    assert len(body["meetings"]) == 2
    assert [m["scheduled_at"] for m in body["meetings"]] == [
        "2026-11-23T04:00:00Z",
        "2026-11-23T12:00:00Z",
    ]
    assert body["meetings"][0]["company"]["bin"] == "700000000001"
    assert body["meetings"][1]["company"]["bin"] == "700000000002"

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CompanyStatus = Literal["new", "no_answer", "refused", "meeting_set"]
MeetingStatus = Literal["scheduled", "cancelled", "completed"]
CallResult = Literal["no_answer", "refused", "meeting_set"]

BIN_PATTERN = re.compile(r"^\d{12}$")
PHONE_ALLOWED_PATTERN = re.compile(r"^\+?[\d\s\-()]+$")


def ensure_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            "Datetime must include timezone information (UTC, ISO 8601, e.g. 2026-11-23T06:00:00Z)."
        )
    return value.astimezone(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class ManagerResponse(BaseModel):
    id: int
    name: str


class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    bin: str = Field(..., description="12-digit Business Identification Number (БИН)")
    phone: str = Field(..., min_length=10, max_length=32)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Company name must not be empty.")
        return cleaned

    @field_validator("bin")
    @classmethod
    def validate_bin(cls, value: str) -> str:
        cleaned = value.strip()
        if not BIN_PATTERN.match(cleaned):
            raise ValueError("BIN must consist of exactly 12 digits.")
        return cleaned

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        cleaned = value.strip()
        if not PHONE_ALLOWED_PATTERN.match(cleaned):
            raise ValueError("Phone contains invalid characters.")
        digits_only = re.sub(r"\D", "", cleaned)
        if not (10 <= len(digits_only) <= 15):
            raise ValueError("Phone must contain between 10 and 15 digits.")
        return cleaned


class CompanyResponse(BaseModel):
    id: int
    name: str
    bin: str
    phone: str
    status: CompanyStatus
    created_at: str


class CompanyListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CompanyResponse]


class MeetingCreate(BaseModel):
    company_id: int = Field(..., gt=0)
    manager_id: int = Field(..., gt=0)
    scheduled_at: datetime

    @field_validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, value: datetime) -> datetime:
        return ensure_utc_aware(value)


class MeetingResponse(BaseModel):
    id: int
    company_id: int
    manager_id: int
    scheduled_at: str
    ends_at: str
    original_scheduled_at: str
    reschedule_count: int
    status: MeetingStatus
    created_at: str
    updated_at: str


class ScheduleMeetingItem(BaseModel):
    id: int
    scheduled_at: str
    ends_at: str
    original_scheduled_at: str
    reschedule_count: int
    status: MeetingStatus
    company: CompanyResponse


class ManagerScheduleResponse(BaseModel):
    manager: ManagerResponse
    date: str
    timezone: str
    meetings: list[ScheduleMeetingItem]


class MeetingUpdate(BaseModel):
    scheduled_at: datetime | None = None
    status: Literal["cancelled", "completed"] | None = None

    @field_validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_utc_aware(value)

    @model_validator(mode="after")
    def validate_patch_payload(self) -> "MeetingUpdate":
        if self.scheduled_at is None and self.status is None:
            raise ValueError("Provide either 'scheduled_at' to reschedule or 'status' to update.")
        if self.scheduled_at is not None and self.status is not None:
            raise ValueError("Cannot reschedule and change status in the same request.")
        return self


class CallCreate(BaseModel):
    company_id: int = Field(..., gt=0)
    manager_id: int = Field(..., gt=0)
    result: CallResult
    meeting_id: int | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_meeting_link(self) -> "CallCreate":
        if self.result == "meeting_set" and self.meeting_id is None:
            raise ValueError("meeting_id is required when result is 'meeting_set'.")
        if self.result != "meeting_set" and self.meeting_id is not None:
            raise ValueError("meeting_id can only be set when result is 'meeting_set'.")
        return self


class CallResponse(BaseModel):
    id: int
    company_id: int
    manager_id: int
    result: CallResult
    meeting_id: int | None
    notes: str | None
    created_at: str

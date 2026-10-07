from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    course_name: str = Field(min_length=1, max_length=200)
    issuer: str = Field(min_length=1, max_length=200)
    issue_date: Optional[date] = None  # defaults to today
    # Recipients are validated individually in the service so one bad entry
    # does not reject the whole request.
    recipients: List[Any] = Field(min_length=1)


class CertificateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    recipient_name: Optional[str]
    recipient_email: Optional[str]
    status: str
    error: Optional[str]
    download_url: Optional[str] = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_name: str
    issuer: str
    issue_date: str
    status: str
    total: int
    succeeded: int
    failed: int
    processed: int
    progress_percent: float
    created_at: datetime
    completed_at: Optional[datetime]
    certificates_url: str
    download_all_url: str


class JobDetail(JobOut):
    errors: List[CertificateOut]  # failed entries, for quick diagnosis

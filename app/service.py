import json
import os
import re
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app import config, pdf
from app.models import Certificate, CertStatus, Job, JobStatus

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_NAME_LEN = 150


def validate_recipient(entry) -> tuple:
    """Return (name, email, error). Error is None when the entry is valid."""
    if not isinstance(entry, dict):
        return None, None, "Recipient must be an object with 'name' and 'email'"
    name = entry.get("name")
    email = entry.get("email")
    name = name.strip() if isinstance(name, str) else name
    email = email.strip().lower() if isinstance(email, str) else email

    errors = []
    if not isinstance(name, str) or not name:
        errors.append("'name' is required")
    elif len(name) > MAX_NAME_LEN:
        errors.append(f"'name' must be at most {MAX_NAME_LEN} characters")
    if not isinstance(email, str) or not EMAIL_RE.match(email):
        errors.append("'email' must be a valid email address")
    return (
        name if isinstance(name, str) else None,
        email if isinstance(email, str) else None,
        "; ".join(errors) or None,
    )


def create_job(db: Session, course_name: str, issuer: str, issue_date, recipients: list) -> Job:
    """Persist the job and one Certificate row per entry. Invalid entries are
    stored as failed immediately; valid ones stay pending for the worker."""
    job = Job(
        course_name=course_name,
        issuer=issuer,
        issue_date=(issue_date or date.today()).isoformat(),
        total=len(recipients),
        status=JobStatus.PENDING,
    )
    seen = set()
    for i, entry in enumerate(recipients):
        name, email, error = validate_recipient(entry)
        if error is None:
            if email in seen:
                error = "Duplicate email within this job"
            seen.add(email)
        try:
            raw = json.dumps(entry)
        except (TypeError, ValueError):
            raw = None
        job.certificates.append(Certificate(
            position=i, recipient_name=name, recipient_email=email, raw_data=raw,
            status=CertStatus.FAILED if error else CertStatus.PENDING, error=error,
        ))
    job.failed = sum(1 for c in job.certificates if c.status == CertStatus.FAILED)
    db.add(job)
    db.commit()
    return job


def finalize(job: Job) -> None:
    job.completed_at = datetime.now(timezone.utc)
    if job.succeeded == job.total:
        job.status = JobStatus.COMPLETED
    elif job.succeeded == 0:
        job.status = JobStatus.FAILED
    else:
        job.status = JobStatus.COMPLETED_WITH_ERRORS


def process_job(session_factory, job_id: str) -> None:
    """Generate all pending certificates. Each certificate is isolated in its
    own try/except and committed, so failures don't affect others and progress
    is visible while the job runs."""
    db = session_factory()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.PROCESSING
        db.commit()

        out_dir = os.path.join(config.CERTIFICATE_DIR, job.id)
        os.makedirs(out_dir, exist_ok=True)

        pending = [c for c in job.certificates if c.status == CertStatus.PENDING]
        for cert in pending:
            path = os.path.join(out_dir, f"{cert.id}.pdf")
            try:
                pdf.render_certificate(path, cert.recipient_name, job.course_name,
                                       job.issuer, job.issue_date, cert.id)
                cert.status, cert.file_path, cert.error = CertStatus.SUCCESS, path, None
                job.succeeded += 1
            except Exception as exc:  # noqa: BLE001 - isolate per-certificate failures
                if os.path.exists(path):
                    os.remove(path)
                cert.status, cert.error = CertStatus.FAILED, f"Generation failed: {exc}"
                job.failed += 1
            db.commit()

        finalize(job)
        db.commit()
    except Exception:  # unexpected job-level failure: don't leave it "processing"
        db.rollback()
        job = db.get(Job, job_id)
        if job is not None:
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
        raise
    finally:
        db.close()

import io
import zipfile
from typing import List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, database, service
from app.database import Base, get_db
from app.models import Certificate, CertStatus, Job, JobStatus
from app.schemas import CertificateOut, JobCreate, JobDetail, JobOut

app = FastAPI(title="Bulk Certificate Generator")
Base.metadata.create_all(database.engine)


def _job_out(job: Job) -> dict:
    processed = job.succeeded + job.failed
    return dict(
        id=job.id, course_name=job.course_name, issuer=job.issuer,
        issue_date=job.issue_date, status=job.status, total=job.total,
        succeeded=job.succeeded, failed=job.failed, processed=processed,
        progress_percent=round(100 * processed / job.total, 1) if job.total else 100.0,
        created_at=job.created_at, completed_at=job.completed_at,
        certificates_url=f"/jobs/{job.id}/certificates",
        download_all_url=f"/jobs/{job.id}/download",
    )


def _cert_out(c: Certificate) -> CertificateOut:
    out = CertificateOut.model_validate(c)
    if c.status == CertStatus.SUCCESS:
        out.download_url = f"/certificates/{c.id}/download"
    return out


def _get_job(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/jobs", response_model=JobOut, status_code=202)
def create_job(payload: JobCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    if len(payload.recipients) > config.MAX_RECIPIENTS_PER_JOB:
        raise HTTPException(413, f"At most {config.MAX_RECIPIENTS_PER_JOB} recipients per job")
    job = service.create_job(db, payload.course_name, payload.issuer,
                             payload.issue_date, payload.recipients)
    if job.failed == job.total:  # nothing to generate
        service.finalize(job)
        db.commit()
    else:
        # Resolved at call time so tests can swap the session factory.
        background.add_task(service.process_job, database.SessionLocal, job.id)
    return _job_out(job)


@app.get("/jobs", response_model=List[JobOut])
def list_jobs(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).order_by(Job.created_at.desc()).limit(limit).offset(offset))
    return [_job_out(j) for j in jobs]


@app.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    data = _job_out(job)
    data["errors"] = [_cert_out(c) for c in job.certificates if c.status == CertStatus.FAILED]
    return data


@app.get("/jobs/{job_id}/certificates", response_model=List[CertificateOut])
def list_certificates(job_id: str,
                      status: Optional[str] = Query(None, pattern="^(pending|success|failed)$"),
                      db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    return [_cert_out(c) for c in job.certificates if status is None or c.status == status]


@app.get("/certificates/{certificate_id}/download")
def download_certificate(certificate_id: str, db: Session = Depends(get_db)):
    cert = db.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(404, "Certificate not found")
    if cert.status != CertStatus.SUCCESS or not cert.file_path:
        raise HTTPException(409, f"Certificate is not available (status: {cert.status})")
    return FileResponse(cert.file_path, media_type="application/pdf",
                        filename=f"certificate_{cert.id}.pdf")


@app.get("/jobs/{job_id}/download")
def download_job_zip(job_id: str, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    if job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
        raise HTTPException(409, "Job is still running")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for c in job.certificates:
            if c.status == CertStatus.SUCCESS and c.file_path:
                safe = "".join(ch if ch.isalnum() else "_" for ch in c.recipient_name)
                zf.write(c.file_path, f"{c.position + 1:05d}_{safe}.pdf")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="job_{job.id}.zip"'})

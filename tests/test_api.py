import io
import zipfile

from app import config, database, pdf, service

GOOD = [{"name": "Alice Smith", "email": "alice@example.com"},
        {"name": "Bob Jones", "email": "bob@example.com"}]


def make(client, recipients, **kw):
    body = {"course_name": "Python 101", "issuer": "Acme Academy", "recipients": recipients}
    body.update(kw)
    return client.post("/jobs", json=body)


def test_create_job_returns_accepted_and_completes(client):
    r = make(client, GOOD)
    assert r.status_code == 202
    job = client.get(f"/jobs/{r.json()['id']}").json()
    assert job["status"] == "completed"
    assert (job["total"], job["succeeded"], job["failed"]) == (2, 2, 0)
    assert job["progress_percent"] == 100.0


def test_request_level_validation(client):
    assert make(client, []).status_code == 422
    assert client.post("/jobs", json={"recipients": GOOD}).status_code == 422
    assert make(client, GOOD, issue_date="not-a-date").status_code == 422


def test_recipient_level_validation_is_partial(client):
    recipients = GOOD + [
        {"name": "", "email": "x@example.com"},
        {"name": "No Email"},
        {"name": "Bad Email", "email": "nope"},
        "not an object",
        {"name": "Dup", "email": "ALICE@example.com"},
    ]
    job = client.get(f"/jobs/{make(client, recipients).json()['id']}").json()
    assert job["status"] == "completed_with_errors"
    assert (job["succeeded"], job["failed"]) == (2, 5)
    assert {e["position"] for e in job["errors"]} == {2, 3, 4, 5, 6}
    assert all(e["error"] for e in job["errors"])


def test_all_invalid_marks_job_failed(client):
    assert make(client, [{"name": ""}]).json()["status"] == "failed"


def test_max_recipients_enforced(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_RECIPIENTS_PER_JOB", 1)
    assert make(client, GOOD).status_code == 413


def test_certificate_generation_produces_pdf(tmp_path):
    p = tmp_path / "c.pdf"
    pdf.render_certificate(str(p), "Zoë Müller", "Course", "Issuer", "2026-01-01", "id-1")
    assert p.read_bytes().startswith(b"%PDF")


def test_individual_failure_does_not_block_others(client, monkeypatch):
    real = pdf.render_certificate

    def flaky(path, name, *a, **kw):
        if name == "Bob Jones":
            raise RuntimeError("boom")
        return real(path, name, *a, **kw)

    monkeypatch.setattr(pdf, "render_certificate", flaky)
    job_id = make(client, GOOD).json()["id"]
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "completed_with_errors"
    assert (job["succeeded"], job["failed"]) == (1, 1)
    assert "boom" in job["errors"][0]["error"]
    assert job["errors"][0]["recipient_name"] == "Bob Jones"


def test_progress_while_pending(client):
    db = database.SessionLocal()
    job = service.create_job(db, "C", "I", None, GOOD)
    r = client.get(f"/jobs/{job.id}").json()
    assert r["status"] == "pending" and r["processed"] == 0 and r["progress_percent"] == 0.0
    assert client.get(f"/certificates/{job.certificates[0].id}/download").status_code == 409
    assert client.get(f"/jobs/{job.id}/download").status_code == 409
    db.close()


def test_retrieve_certificates(client):
    job_id = make(client, GOOD + [{"name": "", "email": "bad"}]).json()["id"]
    certs = client.get(f"/jobs/{job_id}/certificates").json()
    assert len(certs) == 3
    ok = [c for c in certs if c["status"] == "success"]
    assert len(ok) == 2 and ok[0]["download_url"]
    r = client.get(ok[0]["download_url"])
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")

    failed = client.get(f"/jobs/{job_id}/certificates?status=failed").json()
    assert len(failed) == 1
    assert client.get(f"/certificates/{failed[0]['id']}/download").status_code == 409

    z = client.get(f"/jobs/{job_id}/download")
    assert z.status_code == 200
    assert len(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == 2


def test_not_found(client):
    assert client.get("/jobs/nope").status_code == 404
    assert client.get("/certificates/nope/download").status_code == 404

# Bulk Certificate Generator

FastAPI + SQLAlchemy (SQLite by default) + reportlab. Submit many recipients in one
request, get a job id back immediately, poll progress, then download PDFs.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```
## Run
```bash
uvicorn app.main:app --reload
```
Interactive docs: http://127.0.0.1:8000/docs

Config via env vars: `DATABASE_URL` (default `sqlite:///./certificates.db`; any SQLAlchemy URL
e.g. PostgreSQL works), `CERTIFICATE_DIR` (default `./certificates_output`),
`MAX_RECIPIENTS_PER_JOB` (default 5000).

## Tests
```bash
python -m pytest -q
```

## API
| Method | Path | Purpose |
|---|---|---|
| POST | `/jobs` | Create a bulk job (202 Accepted) |
| GET | `/jobs/{id}` | Status, counts, progress %, list of failed entries with reasons |
| GET | `/jobs` | List jobs (`limit`, `offset`) |
| GET | `/jobs/{id}/certificates?status=success\|failed\|pending` | Per-certificate status + `download_url` |
| GET | `/certificates/{id}/download` | One PDF |
| GET | `/jobs/{id}/download` | ZIP of all successful PDFs (409 while job is running) |

### Submit
```bash
curl -X POST localhost:8000/jobs -H 'Content-Type: application/json' -d '{
  "course_name": "Python 101", "issuer": "Acme Academy", "issue_date": "2026-10-01",
  "recipients": [
    {"name": "Alice Smith", "email": "alice@example.com"},
    {"name": "Bob Jones",   "email": "bob@example.com"}
  ]}'
```
Response contains `id`, `status`, counts. `issue_date` is optional (defaults to today).

### Track and retrieve
```bash
curl localhost:8000/jobs/<id>                 # status: pending|processing|completed|completed_with_errors|failed
curl localhost:8000/jobs/<id>/certificates    # each has download_url
curl -o alice.pdf localhost:8000/certificates/<cert_id>/download
curl -o all.zip   localhost:8000/jobs/<id>/download
```

## Design decisions
- **Background processing.** `POST /jobs` validates, stores the job and one row per recipient,
  returns `202` and generates PDFs in a FastAPI `BackgroundTask` (run in a threadpool). A request with
  thousands of recipients therefore doesn't hold the HTTP connection or time out. Progress is committed
  per certificate, so polling shows live counts. Trade-off: the task is in-process, so a server restart
  mid-job leaves it `processing`; for production I'd move to a queue (Celery/RQ) with the same
  `service.process_job` entry point (it only processes `pending` rows, so it can safely be re-run).
- **Two-level validation.** Request-level problems (missing course/issuer, empty list, bad date) → `422`
  for the whole request. Per-recipient problems (missing/long name, invalid email, non-object entry,
  duplicate email in the job) don't reject the request: that entry is recorded as `failed` with a reason
  and the rest proceed. Too many recipients → `413`.
- **Failure isolation.** Each certificate is generated in its own try/except and committed individually.
  Job status: `completed` (all ok), `completed_with_errors`, or `failed` (none succeeded).
  `GET /jobs/{id}` lists failures with positions in the submitted list.
- **Template.** One hard-coded landscape A4 template in `app/pdf.py` (name, course, issuer, date, certificate id).
- **Storage.** PDFs on local disk (`CERTIFICATE_DIR/<job_id>/<cert_id>.pdf`), metadata in the DB.
- **Limits/known gaps.** No authentication, no retry endpoint, tables created with `create_all` (no migrations).
  Characters outside Latin-1 may not render with the built-in Helvetica font (a TTF font would fix that).

# Tracepoint — Digital Evidence Acquisition & Integrity Verification System

A deadline-focused academic prototype for controlled digital evidence file intake, server-side SHA-256 hashing, later integrity verification, chain-of-custody records, forensic working copies, acquisition logs, and PDF reports.

> **Scope and limitations:** This project is not certified forensic imaging software. It does not perform physical disk imaging, deleted-file recovery, RAM forensics, certified hardware acquisition, malware analysis, or courtroom certification. The original is logically immutable through normal application workflows; an administrator with direct storage/database access can still alter files. Use only synthetic/demo evidence for classroom demonstrations.

## Features

- Role-aware login (`ADMIN`, `INVESTIGATOR`, `VIEWER`) with signed short-lived bearer tokens and PBKDF2 password hashes.
- Case creation, listing, search, status and priority filtering, case details, and PDF case reports.
- Controlled evidence uploads with generated storage identifiers, upload-size limit, chunked server-side SHA-256, acquisition log, and initial custody events.
- Evidence detail view with original/current hashes, verification history, custody timeline, forensic copies, and acquisition metadata.
- Integrity verification compares the hash of the stored original with the acquisition hash; mismatches are recorded as `INTEGRITY_FAILED`.
- Forensic copies are independently hashed and checked against the source after copying.
- Persisted chain-of-custody and evidence lifecycle events.
- PDF evidence and case reports.
- Demo seed data with three cases, harmless synthetic text files, real calculated SHA-256 values, custody records, a verified item, and a forensic copy.
- Development-only tamper simulation endpoint, disabled when `DEMO_MODE=false` and restricted to ADMIN.

## Architecture

- **Frontend:** Next.js 14, TypeScript, Tailwind CSS, Recharts, Lucide icons.
- **Backend:** FastAPI, Python, SQLAlchemy.
- **Database:** SQLite by default for fast local demo; PostgreSQL supported through `DATABASE_URL`.
- **Migrations:** Alembic initial schema migration.
- **Storage:** private local directories `backend/storage/originals`, `backend/storage/forensic_copies`, and `backend/storage/reports`. The frontend only sees evidence IDs and metadata, never storage paths.
- **Reports:** ReportLab-generated PDF streams.

## Project structure

```text
digital-evidence-system/
├── backend/
│   ├── app/main.py             # FastAPI application, models, and API routes
│   ├── migrations/             # Alembic schema migrations
│   ├── storage/                # Private originals, copies, and generated reports
│   ├── evidence.db             # Local SQLite database
│   ├── .env.example            # Backend environment template
│   └── requirements.txt
├── frontend/
│   ├── app/                    # Next.js pages
│   ├── components/
│   ├── lib/api.ts              # Shared configured API client
│   └── .env.local.example      # Frontend API URL template
├── start-backend.bat
└── start-frontend.bat
```

## Quick start (local demo)

Requirements: Python 3.11+ and Node.js 18+.

### 1. Backend (Windows PowerShell)

```bash
Set-Location "C:\path\to\digital-evidence-system\backend"
if (!(Test-Path .env)) { Copy-Item .env.example .env }
if (!(Test-Path .venv\Scripts\python.exe)) { py -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

The backend loads `backend/.env`, anchors relative SQLite and storage paths to the backend directory, creates missing schema objects without deleting existing data, and seeds synthetic demo records only when the users table is empty and `DEMO_MODE=true`. Interactive API documentation: http://127.0.0.1:8001/docs. Health endpoint: http://127.0.0.1:8001/health.

### 2. Frontend

In a second terminal:

```bash
Set-Location "C:\path\to\digital-evidence-system\frontend"
if (!(Test-Path .env.local)) { Copy-Item .env.local.example .env.local }
npm install
npm run dev
```

Open http://127.0.0.1:3001. The frontend uses `NEXT_PUBLIC_API_URL=http://127.0.0.1:8001`. This avoids the ambiguous `localhost:8000` route on this machine; the frontend will not connect to MalwareChain. `.env.local` is ignored by Git and contains only the public API base URL, not backend secrets.

The root-level `start-backend.bat` and `start-frontend.bat` scripts also start the services on these ports. Neither script kills existing processes. If 8001 or 3001 is already occupied, identify its owner before choosing another port, then update the frontend URL and backend CORS origins together.

### Demo credentials

- **Admin:** `admin` / `Forensics@123`
- **Investigator:** `investigator` / `Investigator@123`
- **Read-only viewer:** `viewer` / `Viewer@123`

These are demo-only credentials. Change them before any non-local use and do not expose the development server publicly.

## PostgreSQL setup

Create an empty database, install dependencies, and set an environment variable before starting the backend:

```bash
# Example only; replace credentials and database name.
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/evidence_db
```

Set `DATABASE_URL` in your shell or `.env` (load it with your preferred environment loader). For Windows PowerShell, for example:

```powershell
$env:DATABASE_URL="postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/evidence_db"
```

## Database migrations

From `backend/` after installing requirements:

```bash
.\.venv\Scripts\python.exe -m alembic upgrade head
```

To inspect migration state:

```bash
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic history
```

The initial migration creates missing schema objects represented by the SQLAlchemy models. For a local SQLite run, application startup also ensures tables exist. Migrations and the running application use the same backend `.env` database URL.

## API overview

All endpoints except `/health` and `/auth/login` require `Authorization: Bearer <access_token>`.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | API health |
| POST | `/auth/login` | Authenticate and receive token |
| GET | `/auth/me` | Current account and role |
| GET | `/dashboard/stats` | Dashboard counts, distributions, recent activity |
| POST, GET | `/cases` | Create/list/search cases |
| GET, PUT, DELETE | `/cases/{case_id}` | Case detail/update/delete (delete is admin-only and empty cases only) |
| POST, GET | `/evidence` | Upload evidence / list and filter records |
| GET | `/evidence/{evidence_id}` | Evidence detail, custody, copies, verifications, acquisition log |
| POST | `/evidence/{evidence_id}/verify` | Server-side SHA-256 integrity verification |
| POST, GET | `/evidence/{evidence_id}/copies` | Create/list forensic copies |
| GET | `/copies/{copy_id}` | Forensic copy metadata |
| GET, POST | `/evidence/{evidence_id}/custody` | Read/add custody events |
| PATCH | `/evidence/{evidence_id}/status` | Change evidence lifecycle status and record event |
| GET | `/evidence/{evidence_id}/acquisition` | Acquisition log history |
| GET | `/evidence/{evidence_id}/download` | Download original and record access event |
| GET | `/cases/{case_id}/report` | Download case PDF report |
| GET | `/evidence/{evidence_id}/report` | Download evidence PDF report |
| POST | `/dev/evidence/{evidence_id}/simulate-tamper` | **Development only:** alter one byte to demonstrate tamper detection; ADMIN only and hidden when `DEMO_MODE=false` |

## Exact demo workflow

1. Start backend and frontend; sign in as `admin`.
2. Show the populated dashboard and explain the sample data is synthetic.
3. Open **Investigations** and open a case; show associated evidence.
4. Go to **Evidence vault → Register evidence**. Select a case, enter metadata, upload a small `.txt` file, and acquire it.
5. Open the new evidence detail page and point out the server-generated original SHA-256 and acquisition/custody records.
6. Click **Verify integrity**. The result should be `VERIFIED`, with expected and actual hashes matching.
7. Click **Create copy**. Show the independent copy SHA-256 and timestamp.
8. Click **Record transfer** and save a transfer event; show it in the custody timeline.
9. Generate the evidence PDF report and a case PDF report from **Reports**.
10. For tamper detection, use an admin account and POST to `/dev/evidence/{id}/simulate-tamper` from `/docs` for the newly uploaded evidence. Then click **Verify integrity** on its detail page. It should report `INTEGRITY_FAILED` because one byte in the stored file changed. This is deliberately destructive to that demo item; create a fresh sample item if you want a clean pass result again.
11. Demonstrate role restrictions by signing out and signing in as `viewer`; write operations should return `403`.

## Security notes

- SHA-256 is calculated by the backend in 1 MiB chunks; client-provided hashes are not accepted.
- Storage names are random UUIDs; uploaded filenames are metadata, not filesystem paths.
- Upload size is bounded by `MAX_UPLOAD_MB` (default 50 MB).
- SQLAlchemy ORM is used for parameterized database operations.
- Secrets are environment-configurable (`APP_SECRET`); replace the default before any non-demo use.
- Set `DEMO_MODE=false` outside a local demo to disable seeded data and the tamper demonstration endpoint.
- The local filesystem is not WORM storage. For production, add hardened identity/session management, immutable or write-protected storage, backups, malware scanning, rate limits, TLS, audit-log protection, and formal security/forensic validation.

## Known limitations

- This is an academic MVP, not a validated forensic product.
- Authentication is deliberately lightweight for local demonstration; tokens are signed but not encrypted, and user administration/password reset is not implemented.
- Original evidence is logically immutable through ordinary UI/API actions, not protected against an OS/database administrator.
- Dashboard chart trend is illustrative; headline counts and status distributions come from the API.
- PostgreSQL support is configured via SQLAlchemy but should be smoke-tested in the target environment before a live deployment.
- Reports are not digitally signed or certified.

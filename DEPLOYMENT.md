









# Auto Email Extraction Deployment

This deployment keeps the ingestion pipeline always running with:
- one scheduler (`python main.py scheduler`)
- three Celery workers (`high_priority`, `heavy_ai`, `io_bound`)
- Redis broker

## 1) Environment preparation

Use `.env` and ensure these values are set:
- `METAFORGE_API_URL`
- `METAFORGE_REQUIREMENTS_ENDPOINT=api/internal/requirements/ingest-email`
- `METAFORGE_API_KEY` (must match backend `INTERNAL_AUTOMATION_API_KEY`)
- `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`
- `OPENAI_API_KEY`
- `MAILBOX_UPN`

Optional scheduler controls:
- `SCHEDULER_POLL_SECONDS`
- `SCHEDULER_ERROR_BACKOFF_SECONDS`
- `SCHEDULER_HEARTBEAT_PATH`
- `FILE_LISTENER_ENABLED`
- `FILE_LISTENER_INBOX_DIR`
- `FILE_LISTENER_ARCHIVE_DIR`

## 2) Docker Compose (recommended)

From this folder:

```bash
docker compose up -d --build
```

Check status:

```bash
docker compose ps
docker compose logs -f scheduler
```

Stop:

```bash
docker compose down
```

## 3) Windows Services with NSSM

Prerequisites:
- Python virtual environment created at `.venv`
- dependencies installed in `.venv`
- [NSSM](https://nssm.cc/download) downloaded

Install/start services (run PowerShell as Administrator):

```powershell
.\scripts\windows\install-services.ps1 -NssmPath "C:\tools\nssm\nssm.exe"
```

Remove services:

```powershell
.\scripts\windows\uninstall-services.ps1 -NssmPath "C:\tools\nssm\nssm.exe"
```

Service logs are written to:
- `data/service-logs/*.out.log`
- `data/service-logs/*.err.log`

## 4) Health / monitoring

Scheduler heartbeat JSON:
- `data/scheduler_heartbeat.json`

Expected statuses:
- `running`
- `degraded`
- `stopped`

### File listener

Scheduler cycle also checks a local drop folder for raw requirement mails:
- inbox: `data/mail-drop/inbox`
- archive: `data/mail-drop/archive`

Supported file types:
- `.txt` (plain mail body)
- `.json` (optional keys: `subject`, `from_email`, `from_name`, `body`, `receivedDateTime`)

If a new file contains requirement content, it is parsed and auto-created in requirements page through the internal ingestion API.

### Historical autofill for missing fields

When current email extraction misses fields, the pipeline now auto-fills from similar previous requirements:
- primary match: same `requirement_from` + same/similar `job_title`
- fallback match: latest by `requirement_from`

Autofill can populate fields like:
- `work_mode`, `location`, `notice_period`, `overall_experience`
- `employment_type`, `budget_currency`, `yearly_budget`, `monthly_budget`
- `mandatory_skills`, `skills`

Autofill traceability:
- payload includes `autofillMeta` with field-level confidence
- backend activity log stores this metadata for recruiter visibility

Heartbeat checker command:

```powershell
.\.venv\Scripts\python.exe .\scripts\check_heartbeat.py --heartbeat-path .\data\scheduler_heartbeat.json --max-age-seconds 300
```

Exit codes:
- `0` healthy (`running` / `degraded` and fresh)
- `1` fresh but non-running status
- `2` stale heartbeat or invalid/missing heartbeat file

### Task Scheduler monitor (Windows)

Create a Windows Task Scheduler task that runs every 5 minutes:

```powershell
.\scripts\windows\check-heartbeat.ps1 -MaxAgeSeconds 300
```

Suggested action on non-zero exit:
- send email notification (Ops mailbox)
- write to Windows Event Log / SIEM
- optionally restart scheduler service (`MetaForgeEmailPipeline-Scheduler`)

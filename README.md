# Auto Email Extraction & Requirements Processing Pipeline

An automated email extraction, parsing, and normalization pipeline designed to process recruitment requirement emails from Outlook / Microsoft Graph API, structure the data using AI and deterministic heuristics, store them into persistent storage, and serve them via an interactive web interface.

---

## 🚀 Features

- **Automated Email Ingestion**: Connects to Microsoft Graph API / Outlook Mailbox to retrieve requirement emails.
- **AI & Heuristic Information Extraction**: Extracts job titles, client details, mandatory skills, experience, location, budget, and open positions.
- **Continuous Ingestion Scheduler**: Always-on background scheduler supervising inbox scanning and task enqueuing.
- **Requirements Explorer UI**: Flask-based web dashboard (`ui/`) for searching, filtering, and inspecting extracted client requirements.
- **Comprehensive Verification & Alerts**: Rule validation, deduplication, status tracking, and error backoff handling.

---

## 🛠️ Project Structure

```text
Auto_email_extraction/
├── ui/                   # Flask web interface, templates, static assets, and DB layer
│   ├── app.py            # Web application entry point
│   ├── db.py             # Database query and read-only helper functions
│   ├── config.json       # UI and pagination configuration
│   ├── templates/        # HTML templates
│   └── static/           # CSS and client scripts
├── main.py               # Main CLI pipeline & scheduler entry point
├── models.py             # Pydantic schemas and data models
├── requirement_parser.py # Requirement parsing and extraction engine
├── email_filter.py       # Rule-based and classifier email filtering
├── processed_store.py    # SQLite / persistent storage operations
├── config.py             # Central application configuration
├── tests/                # Test suite
├── Dockerfile            # Container definition
├── docker-compose.yml    # Service orchestration (Scheduler, Celery, Redis)
└── requirements.txt      # Python dependencies
```

---

## ⚙️ Quick Start

### 1. Setup Environment
Clone the repository and install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Settings
Copy `.env.example` to `.env` and fill in your Microsoft Graph and MetaForge API credentials:
```bash
cp .env.example .env
```

### 3. Run Web UI
```bash
python ui/app.py
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

### 4. Run Pipeline or Scheduler
```bash
# Run one-off pipeline processing
python main.py pipeline

# Run continuous background scheduler
python main.py scheduler
```

---

## 🧪 Testing

Run test suite:
```bash
pytest
```

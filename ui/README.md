# Recruiter Application Requirements Explorer UI

A lightweight, high-performance, read-only web interface built with Flask, HTML5, Vanilla CSS, and JavaScript to view and inspect all extracted client requirements.

---

## Key Features

1. **Strict Read-Only Architecture**:
   - Opens SQLite database connections strictly in URI read-only mode (`mode=ro`).
   - The UI never performs `INSERT`, `UPDATE`, or `DELETE` operations and never invokes pipeline sync endpoints (`send_to_metaforge`).

2. **Zero Hardcoding**:
   - Database paths, host, port, table column headers, field labels, status badge colors, and autocomplete limits are fully driven by `ui/config.json` or environment variables.

3. **Instant Lookup & Autofill**:
   - Interactive search bar on every page with datalist autocomplete suggestions (`/api/req-ids?prefix=...`).
   - Autofills requirement details dynamically via JSON API (`/api/requirement/<req_id>`) without requiring a full page reload.

4. **Filtering, Sorting & Pagination**:
   - Full-text search across all stored requirement fields.
   - Dynamic client & status filter dropdowns.
   - Column sorting and configurable pagination.

---

## Quick Start

### 1. Run the Web Server

```bash
python ui/app.py
```

The application will bind to `http://127.0.0.1:5000` by default.

---

## Configuration Options

Configurations can be set in `ui/config.json` or overridden via Environment Variables:

| Environment Variable | Default Value | Description |
| :--- | :--- | :--- |
| `UI_HOST` | `127.0.0.1` | Host interface to bind |
| `UI_PORT` | `5000` | Port to listen on |
| `UI_DB_PATH` | `data/metaforge_requirements.db` | Override SQLite database file path |
| `UI_PASSWORD` | *(None)* | Optional password to enable HTTP Basic Authentication |
| `UI_CONFIG_PATH` | `ui/config.json` | Path to JSON configuration file |

---

## Running Unit Tests

```bash
python -m unittest ui/tests/test_ui.py
```

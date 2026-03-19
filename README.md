# Motive Insights Export

Small local Python script to export **Motive Insights** data day-by-day and combine results into a single CSV with an explicit `date` column.

**Why:** The dashboard "Download report" does not include date/time, so you cannot easily get per-day breakdowns. This script loops over a date range, calls the download-insights API (e.g. `/api/v1/downloadinsights`), and writes one CSV with a `date` column for each day.

---

## Setup

**1. Create a virtual environment and install dependencies:**

```bash
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**2. Create a `.env` file** in the project root with your credentials and options (see [Environment variables](#environment-variables) below). Example:

```bash
# Required
GLEAN_BASE_URL=https://instance-be.glean.com
GLEAN_COOKIE=<paste full Cookie header from browser>
GLEAN_ACTAS_EMAIL=user@customer.com

# Optional: if your setup uses an ActAs token
# GLEAN_ACTAS_TOKEN=<token>

# Optional: output path, throttling, timeouts
# OUT_CSV=motive_insights_daily.csv
# SLEEP_SECS=0.3
# TIMEOUT_SECS=60
# MAX_RETRIES=3
```

**Security:** Do not paste cookies or tokens into code. Keep all secrets in `.env` (gitignored). The script does not log cookies or tokens.

---

## How to run

From the project root (with the venv activated):

```bash
.venv/bin/python src/export_daily_insights.py
```

If your shell already has the venv activated (`source .venv/bin/activate`), you can use:

```bash
python src/export_daily_insights.py
```

Output is written to the path in `OUT_CSV` (default: `motive_insights_daily.csv`).

### Options

| Mode | Command |
|------|--------|
| **Single day (default: today)** | `python src/export_daily_insights.py` |
| **Specific day** | `python src/export_daily_insights.py --date 2026-03-15` |
| **Last N days (including today)** | `python src/export_daily_insights.py --days 5` |
| **Custom date range** | `python src/export_daily_insights.py --start 2026-01-01 --end 2026-02-28` |

- With no flags, the script runs **once for today** (one request).
- `--days N`: exports the last N days including today; one request per day, all appended to one CSV.
- `--start` and `--end`: must be used together; exports every day in that range (inclusive).
- Rows with no activity (all zeros in the activity columns) are excluded from the output.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GLEAN_BASE_URL` | Yes | Backend base URL (e.g. `https://<motive>-be.glean.com`). |
| `GLEAN_COOKIE` | Yes | Full Cookie header string from the browser. |
| `GLEAN_ACTAS_EMAIL` or `ACT_AS_EMAIL` | Yes | Customer user email for ActAs. |
| `GLEAN_ACTAS_TOKEN` or `ACTAS_TOKEN` | No | If your setup uses an ActAs token, it is appended to the cookie. |
| `GLEAN_ENDPOINT` | No | API path (default: `/api/v1/downloadinsights`). |
| `OUT_CSV` | No | Output CSV path (default: `motive_insights_daily.csv`). |
| `SLEEP_SECS` | No | Seconds between day requests (default: `0.3`). |
| `TIMEOUT_SECS` | No | Request timeout in seconds (default: `60`). |
| `MAX_RETRIES` | No | Retries for 429/5xx (default: `3`). |
| `LOCALE` | No | Locale for the API (default: `en`). |
| `CLIENT_VERSION` | No | Optional client version query param. |
| `CATEGORIES_JSON` | No | JSON array of categories (default: `["USERS"]`). |
| `DEPARTMENTS_JSON` | No | JSON array of department filters (default: `[]`). |
| `ORIGIN`, `REFERER`, `USER_AGENT` | No | Override request headers if needed. |

---

## Output CSV columns

- `date` — the day (YYYY-MM-DD) for the row  
- `name`, `email`, `department`, `title`, `manager`  
- `days_active_in_period`, `searches_in_period`, `assistant_actions_in_period`, `agent_runs_in_period`, `active_client_sessions_in_period`

Missing values are written as empty string or `0` as appropriate. Rows with no activity in the period are omitted.

---

## Notes

- **Dashboard export vs this script:** The built-in dashboard export does not include date/time, so you cannot tell which day each row refers to. This script adds an explicit `date` column by requesting one day at a time and tagging each row.
- The script uses POST requests with retries and exponential backoff for 429 and 5xx responses.
- No repo is required; this is a local, one-off style project. Use `.gitignore` and keep secrets in `.env` if you version it.

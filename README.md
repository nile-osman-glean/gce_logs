# Motive Insights Export

Small local Python script to export **Motive Insights** data day-by-day and combine results into a single CSV with an explicit `date` column.

**Why:** The dashboard "Download report" does not include date/time, so you cannot easily get per-day breakdowns. This script loops over a date range, calls the same backend (e.g. `/rest/api/v1/insights`), and writes one CSV with a `date` column for each day.

---

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy the example env file and fill in your values:

```bash
cp .env.example .env
# Edit .env with your GLEAN_BASE_URL, GLEAN_COOKIE, GLEAN_ACTAS_EMAIL, START_DATE, END_DATE, etc.
```

**Security:** Do not paste cookies or tokens into code. Keep all secrets in `.env` (gitignored). The script does not log cookies or tokens.

---

## How to run

From the project root:

```bash
.venv/bin/python src/export_daily_insights.py
```

(If `python` is aliased to a system interpreter, use `.venv/bin/python` so the venv’s dependencies are used.)

Output goes to the path set in `OUT_CSV` (default: `motive_users_daily.csv`).

### Automated timeline export

**First N days of current month:**

```bash
.venv/bin/python src/export_daily_insights.py --days 5
```

This exports **day 01 through day N of the current month** (e.g. if today is the 6th, `--days 5` gives 01, 02, 03, 04, 05). One API request per day, all rows appended to one CSV with a `date` column. Never goes past today. Rows with no activity (all zeros) are excluded.

**Single day (one request, one day’s rows):**

```bash
.venv/bin/python src/export_daily_insights.py --single
```

Uses `START_DATE` from `.env` only; one request, one day of data.

**Custom date range:**

```bash
.venv/bin/python src/export_daily_insights.py --start 2026-01-01 --end 2026-02-28
```

Exports every day from `--start` through `--end` (inclusive). One request per day, all appended to one CSV. You must pass both `--start` and `--end`.

**Default: one day = today (run once)**  
With no flags, the script runs **once** for **today** (one request). Use `--date YYYY-MM-DD` for a specific single day, `--days N` for first N days of the month, or `--start` / `--end` for a custom range.

---

## Obtaining the request payload

The script uses a **request body template** that must match what the Insights "Download report" uses:

1. Open Chrome DevTools → **Network**.
2. In the Motive Insights UI, click **Download report** (or trigger the same request).
3. Find the request to the insights API (e.g. `insights` or `/rest/api/v1/insights`).
4. Right‑click the request → **Copy** → **Copy as cURL**.
5. From the cURL command, copy the **JSON body** (the part after `-d '...'` or `--data-raw '...'`).
6. Paste that JSON into `REQUEST_BODY_TEMPLATE` in `src/export_daily_insights.py`.

The script will overwrite `overviewRequest.dayRange` for each day (UTC 00:00:00–23:59:59), so you only need to ensure the rest of the body (filters, etc.) matches. The day range is set under `overviewRequest.dayRange` to match the newer Insights overview behavior.

---

## Environment variables

| Variable | Description |
|----------|-------------|
| `GLEAN_BASE_URL` | Backend base URL (e.g. `https://<motive>-be.glean.com`). |
| `GLEAN_ENDPOINT` | API path (default: `/rest/api/v1/insights`). |
| `GLEAN_COOKIE` | Full Cookie header string from the browser. |
| `GLEAN_ACTAS_EMAIL` | Customer user email for `X-Glean-ActAs`. |
| `START_DATE` | Start of range, `YYYY-MM-DD`. |
| `END_DATE` | End of range (inclusive), `YYYY-MM-DD`. |
| `OUT_CSV` | Output CSV path (default: `motive_insights_daily.csv`). |
| `SLEEP_SECS` | Seconds to sleep between day requests (default: `0.3`). |

---

## Output CSV columns

- `date` — the day (YYYY-MM-DD) for the row  
- `name`, `email`, `department`, `title`, `manager`  
- `days_active_in_period`, `searches_in_period`, `assistant_actions_in_period`, `agent_runs_in_period`, `active_client_sessions_in_period`

Missing values are written as empty string or `0` as appropriate.

---

## Notes

- **Dashboard export vs this script:** The built-in dashboard export does not include date/time, so you cannot tell which day each row refers to. This script adds an explicit `date` column by requesting one day at a time and tagging each row.
- No repo is required; this is a local, one-off style project. Use `.gitignore` and `.env.example` as provided if you ever version it.

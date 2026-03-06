import argparse
import csv
import datetime as dt
import io
import json
import os
import time
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from dotenv import load_dotenv

DEFAULT_ENDPOINT = "/api/v1/downloadinsights"
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

def get_env(name: str, default: str | None = None, required: bool = False) -> str:
    v = os.getenv(name, default)
    if required and (v is None or str(v).strip() == ""):
        raise SystemExit(f"Missing required env var: {name}")
    return str(v)

def parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)

def daterange_inclusive(start: dt.date, end: dt.date):
    cur = start
    one = dt.timedelta(days=1)
    while cur <= end:
        yield cur
        cur += one

def safe_json_loads(s: str, fallback):
    try:
        return json.loads(s)
    except Exception:
        return fallback

def request_with_retries(session: requests.Session, url: str, headers: dict, body: dict,
                         timeout: int, max_retries: int) -> requests.Response:
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            resp = session.post(url, headers=headers, json=body, timeout=timeout)
            if resp.status_code in RETRYABLE_STATUSES:
                # exponential backoff: 1,2,4,... (cap 30)
                sleep_s = min(30.0, 2 ** attempt)
                ra = resp.headers.get("Retry-After")
                if ra:
                    try:
                        sleep_s = max(sleep_s, float(ra))
                    except ValueError:
                        pass
                time.sleep(sleep_s)
                continue
            return resp
        except requests.RequestException as e:
            last_exc = e
            time.sleep(min(30.0, 2 ** attempt))
            continue

    if last_exc:
        raise last_exc
    raise RuntimeError("Exhausted retries")

def decode_csv_bytes(b: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8")

def parse_csv(text: str) -> tuple[list[str], list[list[str]]]:
    f = io.StringIO(text)
    reader = csv.reader(f)
    rows = [r for r in reader if any((c or "").strip() for c in r)]
    if not rows:
        raise ValueError("Empty CSV response")
    return rows[0], rows[1:]


def _row_has_activity(row: list[str], activity_cols: int = 5) -> bool:
    """True if at least one of the last activity_cols values is non-zero."""
    if len(row) < activity_cols:
        return True  # keep row if we can't parse
    for cell in row[-activity_cols:]:
        try:
            if int(cell.strip() or 0) != 0:
                return True
        except ValueError:
            pass
    return False

def main() -> int:
    parser = argparse.ArgumentParser(description="Export Motive Insights day-by-day to one CSV.")
    parser.add_argument("--debug", action="store_true", help="Print request URL/headers/body (secrets redacted) and exit.")
    parser.add_argument("--single", action="store_true", help="One request only (same as default).")
    parser.add_argument("--days", type=int, metavar="N", help="Export first N days of current month (01..N, not past today).")
    parser.add_argument("--start", type=str, metavar="YYYY-MM-DD", help="Start of range (use with --end).")
    parser.add_argument("--end", type=str, metavar="YYYY-MM-DD", help="End of range (use with --start).")
    parser.add_argument("--date", type=str, metavar="YYYY-MM-DD", help="Export this single day (default when no flags: today).")
    args = parser.parse_args()

    load_dotenv()

    base_url = get_env("GLEAN_BASE_URL", required=True).rstrip("/")
    endpoint = get_env("GLEAN_ENDPOINT", DEFAULT_ENDPOINT).strip()
    actas_email = get_env("GLEAN_ACTAS_EMAIL") or get_env("ACT_AS_EMAIL") or ""
    if not actas_email.strip():
        raise SystemExit("Missing required env var: GLEAN_ACTAS_EMAIL (or ACT_AS_EMAIL)")
    actas_email = actas_email.strip()
    cookie_header = get_env("GLEAN_COOKIE", required=True)
    actas_token = (get_env("GLEAN_ACTAS_TOKEN") or get_env("ACTAS_TOKEN") or "").strip()
    if actas_token:
        cookie_header = (cookie_header.rstrip("; ") + "; Actas-Token=" + actas_token)

    today_utc = dt.datetime.now(dt.timezone.utc).date()
    if args.days is not None:
        if args.days < 1:
            raise SystemExit("--days must be >= 1")
        # First N days of current month (01, 02, ..., N), not past today
        start_date = today_utc.replace(day=1)
        last_day = min(args.days, today_utc.day)
        end_date = start_date + dt.timedelta(days=last_day - 1)
        print(f"Timeline: days 1–{last_day} of month ({start_date} to {end_date})", flush=True)
    elif args.start and args.end:
        start_date = parse_date(args.start.strip())
        end_date = parse_date(args.end.strip())
        if start_date > end_date:
            raise SystemExit("--start must be <= --end")
        if end_date > today_utc:
            raise SystemExit(f"--end {end_date} is in the future (UTC today: {today_utc}).")
        print(f"Timeline: {start_date} to {end_date}", flush=True)
    elif args.start or args.end:
        raise SystemExit("Use both --start and --end for a date range.")
    else:
        # Single day: --date YYYY-MM-DD or today
        if args.date:
            start_date = parse_date(args.date.strip())
            if start_date > today_utc:
                raise SystemExit(f"--date {start_date} is in the future (UTC today: {today_utc}).")
        else:
            start_date = today_utc
        end_date = start_date
        print(f"Timeline: single day ({start_date})", flush=True)
    out_csv = get_env("OUT_CSV", "motive_insights_daily.csv")

    sleep_secs = float(get_env("SLEEP_SECS", "0.3"))
    timeout = int(get_env("TIMEOUT_SECS", "60"))
    max_retries = int(get_env("MAX_RETRIES", "3"))

    locale = get_env("LOCALE", "en")
    client_version = get_env("CLIENT_VERSION", "").strip()

    categories = safe_json_loads(get_env("CATEGORIES_JSON", '["USERS"]'), ["USERS"])
    departments = safe_json_loads(get_env("DEPARTMENTS_JSON", "[]"), [])

    if start_date > end_date:
        raise SystemExit("START_DATE must be <= END_DATE")
    if args.single:
        end_date = start_date  # one day only, one request

    # Build URL
    params = {"actas": actas_email, "locale": locale}
    if client_version:
        params["clientVersion"] = client_version
    url = urljoin(base_url + "/", endpoint.lstrip("/")) + "?" + urlencode(params)

    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Cookie": cookie_header,
        "Origin": get_env("ORIGIN", "https://app.glean.com"),
        "Referer": get_env("REFERER", "https://app.glean.com/"),
        "User-Agent": get_env(
            "USER_AGENT",
            "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36",
        ),
        "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "priority": "u=1, i",
    }

    # Always print request URL (actas redacted) so you can verify it matches the cURL
    _parsed = urlparse(url)
    _qs = parse_qs(_parsed.query)
    if "actas" in _qs:
        _qs["actas"] = ["<REDACTED>"]
    _safe_query = urlencode([(k, v[0]) for k, v in _qs.items()], doseq=False)
    _display_url = urlunparse((_parsed.scheme, _parsed.netloc, _parsed.path, _parsed.params, _safe_query, _parsed.fragment))
    print("Request URL:", _display_url, flush=True)

    session = requests.Session()

    # Debug: print request (secrets redacted) and exit
    if args.debug:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "actas" in qs:
            qs["actas"] = ["<REDACTED>"]
        redacted_query = urlencode([(k, v[0]) for k, v in qs.items()], doseq=False)
        debug_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, redacted_query, parsed.fragment))
        debug_headers = {k: ("<REDACTED>" if k.lower() == "cookie" else v) for k, v in headers.items()}
        first_day = next(daterange_inclusive(start_date, end_date))
        days_from_now = (today_utc - first_day).days
        debug_body = {
            "categories": categories,
            "dayRange": {"start": {"daysFromNow": days_from_now}, "end": {"daysFromNow": days_from_now}},
            "departments": departments,
        }
        print("--debug: request that would be sent (first day)", flush=True)
        print("URL:", debug_url, flush=True)
        print("Headers:", json.dumps(debug_headers, indent=2), flush=True)
        print("Body:", json.dumps(debug_body, indent=2), flush=True)
        return 0

    expected_header = None
    wrote_header = False

    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as out_f:
        out_w = csv.writer(out_f)

        for day in daterange_inclusive(start_date, end_date):
            day_iso = day.isoformat()
            days_from_now = (today_utc - day).days  # 0=today, 1=yesterday, etc.

            body = {
                "categories": categories,
                "dayRange": {"start": {"daysFromNow": days_from_now}, "end": {"daysFromNow": days_from_now}},
                "departments": departments,
            }

            resp = request_with_retries(session, url, headers, body, timeout, max_retries)
            if resp.status_code != 200:
                ct = resp.headers.get("content-type", "")
                snippet = resp.text[:500] if "text" in ct or ct == "" else "<non-text response>"
                raise SystemExit(f"{day_iso}: HTTP {resp.status_code}. Content-Type={ct}. Snippet={snippet!r}")

            ct = (resp.headers.get("content-type") or "").lower()
            if "application/json" in ct:
                # often an error payload
                try:
                    err = resp.json()
                except Exception:
                    err = {"raw": resp.text[:1000]}
                raise SystemExit(f"{day_iso}: Expected CSV, got JSON: {err}")

            header, rows = parse_csv(decode_csv_bytes(resp.content))

            if expected_header is None:
                expected_header = header
            elif header != expected_header:
                raise SystemExit(
                    f"{day_iso}: CSV header changed.\nExpected: {expected_header}\nGot: {header}"
                )

            # Exclude rows with no activity (all zeros in last 5 columns)
            active_rows = [r for r in rows if _row_has_activity(r)]

            if not wrote_header:
                out_w.writerow(["date"] + header)
                wrote_header = True

            for r in active_rows:
                out_w.writerow([day_iso] + r)

            out_f.flush()
            print(f"{day_iso}: wrote {len(active_rows)} rows (excluded {len(rows) - len(active_rows)} with no activity)", flush=True)
            time.sleep(max(0.0, sleep_secs))

    print(f"Done. Output: {out_csv}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
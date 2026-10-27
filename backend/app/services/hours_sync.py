"""Keep operating_hours in step with TTU's published hours page.

The page has one table with a "Climbing Wall Hours" column and a row per weekday
("2 PM - 7 PM" or "Closed"). The sync only writes when all seven days parse, so a page
redesign leaves the last good hours in place and reports the problem in the admin portal.
"""
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import os
import re
import urllib.request

from .database_service import db_session
from .schedule_service import WEEKDAYS, setting
from .time_service import now_utc

SOURCE_URL = os.environ.get("ROCKWALL_HOURS_URL", "https://www.tntech.edu/recreation/hours.php")
SYNC_EVERY = timedelta(hours=6)
TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?|noon", re.IGNORECASE)


class _Tables(HTMLParser):
    """Collects every table as rows of cell text."""

    def __init__(self):
        super().__init__()
        self.tables, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.tables[-1].append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def _clock(match):
    word = match.group(0).lower()
    if word == "noon":
        return "12:00"
    hour, minute, half = int(match.group(1)), int(match.group(2) or 0), match.group(3).lower()
    if not (1 <= hour <= 12 and 0 <= minute < 60):
        raise ValueError(f"Unreadable time {match.group(0)!r}")
    return f"{hour % 12 + (12 if half == 'p' else 0):02d}:{minute:02d}"


def parse_range(text):
    """'2 PM - 7 PM' -> ('14:00', '19:00'); 'Closed' -> None."""
    if re.search(r"\bclosed\b", text, re.IGNORECASE):
        return None
    times = [_clock(m) for m in TIME_RE.finditer(text)]
    if len(times) != 2 or "/" in text:
        raise ValueError(f"Unreadable hours {text!r}")
    opens, closes = times
    if not opens < closes:
        raise ValueError(f"Closing time is not after opening time in {text!r}")
    return opens, closes


def parse_hours(html):
    parser = _Tables()
    parser.feed(html)
    for table in parser.tables:
        header = next((row for row in table if any("climbing" in cell.lower() for cell in row)), None)
        if header is None:
            continue
        column = next(i for i, cell in enumerate(header) if "climbing" in cell.lower())
        hours = {}
        for row in table:
            if row and row[0].strip().title() in WEEKDAYS and len(row) > column:
                hours[WEEKDAYS.index(row[0].strip().title())] = parse_range(row[column])
        if len(hours) != 7:
            raise ValueError(f"Found {len(hours)} of 7 days in the Climbing Wall column")
        return hours
    raise ValueError("No 'Climbing Wall' column on the hours page")


def fetch_page(url=SOURCE_URL):
    request = urllib.request.Request(url, headers={"User-Agent": "TTU-Rockwall-hours-sync/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read(2_000_000).decode("utf-8", errors="replace")


def _record(status):
    with db_session(write=True) as db:
        db.execute("UPDATE settings SET v=? WHERE k='hours_sync_status'", (status,))
        db.execute("UPDATE settings SET v=? WHERE k='hours_synced_at'", (now_utc(),))


def sync_hours(force=False, fetch=fetch_page):
    """Fetch, parse and store the weekly hours. Returns the status message saved for admins."""
    with db_session() as db:
        if not force and setting(db, "hours_auto_sync") != "1":
            return "Auto-sync is off."
    try:
        hours = parse_hours(fetch())
    except Exception as error:  # network or parse problem: keep the last good hours
        status = f"Sync failed, kept the current hours: {error}"
        _record(status)
        return status
    with db_session(write=True) as db:
        before = {r[0]: (r[1], r[2]) for r in db.execute("SELECT weekday,opens,closes FROM operating_hours")}
        for weekday, value in hours.items():
            db.execute("UPDATE operating_hours SET opens=?,closes=? WHERE weekday=?",
                       (value[0] if value else None, value[1] if value else None, weekday))
        after = {r[0]: (r[1], r[2]) for r in db.execute("SELECT weekday,opens,closes FROM operating_hours")}
    changed = [WEEKDAYS[d] for d in range(7) if before.get(d) != after.get(d)]
    status = f"Synced from tntech.edu. {'Changed: ' + ', '.join(changed) + '.' if changed else 'No changes.'}"
    _record(status)
    return status


def sync_if_due():
    if os.environ.get("ROCKWALL_HOURS_SYNC", "1") != "1":
        return None
    with db_session() as db:
        if setting(db, "hours_auto_sync") != "1":
            return None
        last = setting(db, "hours_synced_at") or ""
    if last and datetime.fromisoformat(last) > datetime.now(timezone.utc) - SYNC_EVERY:
        return None
    return sync_hours()

"""Opening hours, the bookable time grid, and per-slot online availability.

Everything that decides "is the wall open" reads operating_hours + closures, so when the
weekly hours change (auto-synced from TTU's hours page, or edited by an admin) the booking
window, the homepage status line and booking validation all follow automatically.
"""
from datetime import date, datetime, timedelta

from .time_service import booking_time, now_utc, wall_zone

SLOT_MINUTES = 30
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
ACTIVE = ("pending", "confirmed")


def setting(db, key, default=None):
    row = db.execute("SELECT v FROM settings WHERE k=?", (key,)).fetchone()
    return row[0] if row else default


def weekly_hours(db):
    return {r["weekday"]: (r["opens"], r["closes"]) if r["opens"] else None
            for r in db.execute("SELECT * FROM operating_hours ORDER BY weekday")}


def grid(opens, closes):
    """Every bookable boundary from opening to closing, e.g. 14:00, 14:30 … 19:00."""
    current = datetime.strptime(opens, "%H:%M")
    end = datetime.strptime(closes, "%H:%M")
    times = []
    while current <= end:
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=SLOT_MINUTES)
    return times


def day_hours(db, day, weekly=None):
    """Hours for one local calendar day, with closures taking priority over the weekly hours."""
    weekly = weekly if weekly is not None else weekly_hours(db)
    closure = db.execute("SELECT reason FROM closures WHERE day=?", (day.isoformat(),)).fetchone()
    hours = None if closure else weekly.get(day.weekday())
    return {"date": day.isoformat(), "weekday": WEEKDAYS[day.weekday()], "open": hours is not None,
            "opens": hours[0] if hours else None, "closes": hours[1] if hours else None,
            "reason": (closure[0] or "Closed") if closure else None if hours else "Closed"}


def local_now():
    return datetime.fromisoformat(now_utc()).astimezone(wall_zone())


def arrival_options(info, now=None):
    """Arrival times still in the future for a day (the last boundary is closing, so not an arrival)."""
    if not info["open"]:
        return []
    now = now or local_now()
    times = grid(info["opens"], info["closes"])[:-1]
    if info["date"] == now.date().isoformat():
        times = [t for t in times if t > now.strftime("%H:%M")]
    return times


def booking_days(db, now=None):
    """Upcoming days in the booking window. Closed days are dropped here, so the website
    never offers them, and they reappear automatically if the hours change."""
    now = now or local_now()
    weekly = weekly_hours(db)
    window = int(setting(db, "booking_days", "7"))
    days = []
    for offset in range(window):
        info = day_hours(db, now.date() + timedelta(days=offset), weekly)
        info["arrivals"] = arrival_options(info, now)
        if info["arrivals"]:
            days.append(info)
    return days


def status_now(db, now=None):
    """What the homepage says: open now (and until when), or when it next opens."""
    now = now or local_now()
    weekly = weekly_hours(db)
    today = day_hours(db, now.date(), weekly)
    clock = now.strftime("%H:%M")
    if today["open"] and today["opens"] <= clock < today["closes"]:
        return {"open": True, "closes": today["closes"], "next": None}
    for offset in range(0, 15):
        info = day_hours(db, now.date() + timedelta(days=offset), weekly)
        if info["open"] and (offset or clock < info["opens"]):
            return {"open": False, "closes": None,
                    "next": {"date": info["date"], "weekday": info["weekday"], "opens": info["opens"]}}
    return {"open": False, "closes": None, "next": None}


def online_limit(db):
    """Online bookings per slot, never more than the wall can hold."""
    return min(int(setting(db, "online_capacity", "10")), int(setting(db, "capacity_max", "20")))


def reservations_on(db, day, exclude=None):
    start = booking_time(day.isoformat(), "00:00")
    end = booking_time((day + timedelta(days=1)).isoformat(), "00:00")
    return db.execute("""SELECT UniqueID,Arrival_Time,Departure_Time FROM visitorsSignedUp
      WHERE Arrival_Time>=? AND Arrival_Time<? AND Status IN ('pending','confirmed')
      AND (? IS NULL OR UniqueID<>?)""", (start, end, exclude, exclude)).fetchall()


def slot_usage(db, info, exclude=None):
    """Online bookings overlapping each 30-minute slot of an open day."""
    if not info["open"]:
        return []
    limit = online_limit(db)
    rows = reservations_on(db, date.fromisoformat(info["date"]), exclude)
    times = grid(info["opens"], info["closes"])
    slots = []
    for start, end in zip(times, times[1:]):
        a, b = booking_time(info["date"], start), booking_time(info["date"], end)
        booked = sum(1 for r in rows if r["Arrival_Time"] < b and r["Departure_Time"] > a)
        slots.append({"time": start, "end": end, "booked": booked, "remaining": max(0, limit - booked)})
    return slots


def validate_window(db, day_text, arrival, departure, exclude=None, now=None):
    """Check a requested visit against the hours and online capacity.
    Returns (arrival_utc, departure_utc) or raises ValueError with a visitor-facing message."""
    try:
        day = date.fromisoformat(day_text)
    except (TypeError, ValueError):
        raise ValueError("Pick a day from the booking window.")
    now = now or local_now()
    window = int(setting(db, "booking_days", "7"))
    if not now.date() <= day < now.date() + timedelta(days=window):
        raise ValueError(f"Bookings open {window} days ahead. Pick a day in the booking window.")
    info = day_hours(db, day)
    if not info["open"]:
        raise ValueError(f"The wall is closed on {info['weekday']}{' (' + info['reason'] + ')' if info['reason'] != 'Closed' else ''}.")
    times = grid(info["opens"], info["closes"])
    if arrival not in times[:-1] or departure not in times[1:] or departure <= arrival:
        raise ValueError("Pick an arrival and departure from the lists.")
    if arrival not in arrival_options(info, now):
        raise ValueError("That arrival time has already passed. Pick a later time.")
    check_capacity(db, info, arrival, departure, exclude)
    return booking_time(day_text, arrival), booking_time(day_text, departure)


class FullError(ValueError):
    """Online spaces are used up for part of the requested window."""


def check_capacity(db, info, arrival, departure, exclude=None):
    for slot in slot_usage(db, info, exclude):
        if arrival <= slot["time"] < departure and slot["remaining"] <= 0:
            raise FullError(f"Online spaces are full at {slot['time']}. Try another time, or walk in.")

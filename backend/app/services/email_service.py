"""Booking emails: built at booking time, queued in email_outbox, delivered afterwards.

Configure SMTP with ROCKWALL_SMTP_HOST / _PORT / _USER / _PASSWORD / _FROM / _SECURITY
(starttls, ssl or none). Without ROCKWALL_SMTP_HOST, messages are saved as .eml files next
to the database (outbox/) so they can be opened and checked during development.
"""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid
import html
import io
import os
import smtplib
from urllib.parse import quote, urlencode

import segno

from .database_service import database_path, db_session
from .time_service import now_utc, wall_zone

MAX_ATTEMPTS = 5
PURPLE, PURPLE_DARK, GOLD, INK, MUTED, PAPER, LINE = "#4F2D7F", "#2B1A4A", "#FFDD00", "#1F1A24", "#6B6475", "#F5F2EC", "#E6E0D6"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def public_url():
    return os.environ.get("ROCKWALL_PUBLIC_URL", "http://localhost:5173").rstrip("/")


def location():
    return os.environ.get("ROCKWALL_LOCATION", "Climbing Wall, Burnett Recreation Center, Tennessee Tech")


def sender():
    return os.environ.get("ROCKWALL_SMTP_FROM", "TTU Rockwall <no-reply@tntechclimb.com>")


def _local(stamp):
    return datetime.fromisoformat(stamp).astimezone(wall_zone())


def _clock(moment):
    return moment.strftime("%I:%M %p").lstrip("0")


def describe(r):
    start, end = _local(r["Arrival_Time"]), _local(r["Departure_Time"])
    return {"day": f"{start:%A, %B} {start.day}", "short_day": f"{start:%a, %b} {start.day}",
            "window": f"{_clock(start)} – {_clock(end)}", "name": f"{r['FirstName']} {r['LastName']}".strip(),
            "code": r["PickupCode"] or r["ReceiptCode"][:8].upper(), "start": start, "end": end}


def qr_png(text):
    buffer = io.BytesIO()
    segno.make(text, error="m").save(buffer, kind="png", scale=10, border=2, dark=PURPLE_DARK)
    return buffer.getvalue()


def _utc(moment):
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def calendar_link(r, manage):
    d = describe(r)
    return "https://calendar.google.com/calendar/render?" + urlencode({
        "action": "TEMPLATE", "text": "Climbing at the TTU Rockwall",
        "dates": f"{_utc(d['start'])}/{_utc(d['end'])}", "location": location(),
        "details": f"Check-in code: {d['code']}\nManage or cancel: {manage}"})


def ics(r, manage):
    d = describe(r)
    escape = lambda text: text.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")
    return "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TTU Rockwall//Booking//EN", "METHOD:PUBLISH",
        "BEGIN:VEVENT", f"UID:{r['ReceiptCode']}@tntechclimb", f"DTSTAMP:{_utc(datetime.now(timezone.utc))}",
        f"DTSTART:{_utc(d['start'])}", f"DTEND:{_utc(d['end'])}", "SUMMARY:Climbing at the TTU Rockwall",
        f"LOCATION:{escape(location())}", "DESCRIPTION:" + escape(f"Check-in code: {d['code']}. Manage or cancel: {manage}"),
        "BEGIN:VALARM", "TRIGGER:-PT1H", "ACTION:DISPLAY", "DESCRIPTION:Climbing at the TTU Rockwall", "END:VALARM",
        "END:VEVENT", "END:VCALENDAR", ""])


# ---------- HTML building blocks (inline styles + tables: what email clients reliably render) ----------

def _button(href, label, primary=True):
    bg, fg, border = (PURPLE, "#FFFFFF", PURPLE) if primary else ("#FFFFFF", PURPLE, LINE)
    return (f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="display:inline-table;margin:0 6px 10px 0">'
            f'<tr><td style="border-radius:10px;background:{bg};border:1.5px solid {border}">'
            f'<a href="{html.escape(href)}" style="display:inline-block;padding:13px 22px;font:600 15px/1 {FONT};'
            f'color:{fg};text-decoration:none;border-radius:10px">{label}</a></td></tr></table>')


def _row(label, value):
    return (f'<tr><td style="padding:11px 0;border-top:1px solid {LINE};font:500 13px/1.4 {FONT};color:{MUTED};width:96px;vertical-align:top">{label}</td>'
            f'<td style="padding:11px 0;border-top:1px solid {LINE};font:600 15px/1.4 {FONT};color:{INK}">{value}</td></tr>')


def _layout(preheader, band_title, band_sub, body, accent=PURPLE):
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light">
<title>{html.escape(band_title)}</title></head>
<body style="margin:0;padding:0;background:{PAPER};-webkit-text-size-adjust:100%">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{PAPER}">{html.escape(preheader)}&#8199;&#65279;&#847;&#8199;&#65279;&#847;&#8199;&#65279;&#847;</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:{PAPER}">
<tr><td align="center" style="padding:28px 14px 40px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:560px">
<tr><td style="padding:0 6px 16px">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr>
    <td style="font:800 15px/1 {FONT};letter-spacing:.12em;color:{PURPLE}">TTU&nbsp;ROCKWALL</td>
    <td align="right" style="font:500 12px/1 {FONT};color:{MUTED}">Tennessee Tech Campus Recreation</td>
  </tr></table>
</td></tr>
<tr><td style="background:{accent};border-radius:18px 18px 0 0;padding:30px 30px 26px">
  <div style="width:44px;height:5px;background:{GOLD};border-radius:3px;margin:0 0 18px"></div>
  <h1 style="margin:0;font:800 30px/1.15 {FONT};color:#FFFFFF;letter-spacing:-.01em">{band_title}</h1>
  <p style="margin:10px 0 0;font:500 16px/1.45 {FONT};color:#E9E2F5">{band_sub}</p>
</td></tr>
<tr><td style="background:#FFFFFF;border-radius:0 0 18px 18px;padding:28px 30px 30px;border:1px solid {LINE};border-top:0">
{body}
</td></tr>
<tr><td style="padding:22px 10px 0;font:400 12px/1.6 {FONT};color:{MUTED};text-align:center">
  <a href="{html.escape(public_url())}" style="color:{PURPLE};font-weight:600;text-decoration:none">tntechclimb.com</a>
  &nbsp;·&nbsp; <a href="https://www.tntech.edu/recreation/hours.php" style="color:{MUTED}">Hours &amp; closures</a><br>
  You're getting this because a climb was booked with this address at the TTU Rockwall.
</td></tr>
</table></td></tr></table></body></html>"""


def _code_boxes(code):
    cells = "".join(
        f'<td style="padding:0 4px"><div style="width:52px;height:64px;border-radius:12px;background:{PAPER};border:1.5px solid {LINE};'
        f'font:800 34px/64px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:{PURPLE_DARK};text-align:center">{html.escape(ch)}</div></td>'
        for ch in code)
    return f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center"><tr>{cells}</tr></table>'


def _nowrap(*parts):
    return " &nbsp;·&nbsp; ".join(f'<span style="white-space:nowrap">{html.escape(p)}</span>' for p in parts)


def _manage_url(token):
    # The token sits in the fragment (#), which browsers never send to the server,
    # so it can't end up in access logs or Referer headers.
    return f"{public_url()}/booking#token={quote(token)}"


def build_confirmation(r, token):
    d, manage = describe(r), _manage_url(token)
    qr_cid = make_msgid(domain="tntechclimb")
    body = f"""
<p style="margin:0 0 6px;font:700 12px/1 {FONT};letter-spacing:.14em;color:{MUTED};text-align:center">CHECK-IN CODE</p>
{_code_boxes(d['code'])}
<p style="margin:16px 0 0;text-align:center"><img src="cid:{qr_cid[1:-1]}" width="148" height="148" alt="QR code for check-in code {html.escape(d['code'])}"
   style="display:inline-block;border:0;border-radius:10px"></p>
<p style="margin:10px 0 24px;font:400 14px/1.5 {FONT};color:{MUTED};text-align:center">Show the code or scan the QR at the climbing-wall desk when you arrive.</p>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 24px">
{_row('Climber', html.escape(d['name']))}
{_row('Date', html.escape(d['day']))}
{_row('Time', html.escape(d['window']))}
{_row('Where', html.escape(location()))}
</table>
<div style="text-align:left">{_button(calendar_link(r, manage), 'Add to Google Calendar')}{_button(manage, 'Manage or cancel', primary=False)}</div>
<p style="margin:4px 0 22px;font:400 13px/1.5 {FONT};color:{MUTED}">Using Apple Calendar or Outlook? Open the attached <b>rockwall-booking.ics</b>.</p>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:{PAPER};border-radius:14px">
<tr><td style="padding:18px 20px">
  <p style="margin:0 0 10px;font:700 15px/1.3 {FONT};color:{INK}">Before you come</p>
  <p style="margin:0 0 6px;font:400 14px/1.5 {FONT};color:{INK}">• Climbing shoes, harnesses and chalk are free to use.</p>
  <p style="margin:0 0 6px;font:400 14px/1.5 {FONT};color:{INK}">• Wear clothes you can move in.</p>
  <p style="margin:0;font:400 14px/1.5 {FONT};color:{INK}">• Can't make it? <a href="{html.escape(manage)}" style="color:{PURPLE};font-weight:600">Cancel your booking</a> so someone else can climb.</p>
</td></tr></table>"""
    page = _layout(f"{d['short_day']}, {d['window']}. Check-in code {d['code']}.", "You're booked.",
                   _nowrap(d["day"], d["window"]), body)
    text = (f"You're booked at the TTU Rockwall.\n\n"
            f"CHECK-IN CODE: {d['code']}\nShow this code at the climbing-wall desk when you arrive.\n\n"
            f"Climber: {d['name']}\nDate:    {d['day']}\nTime:    {d['window']}\nWhere:   {location()}\n\n"
            f"Add to Google Calendar: {calendar_link(r, manage)}\n"
            f"Manage or cancel: {manage}\n\n"
            f"Before you come\n- Climbing shoes, harnesses and chalk are free to use.\n- Wear clothes you can move in.\n"
            f"- Can't make it? Cancel at the link above so someone else can climb.\n\n{public_url()}\n")
    message = _envelope(r["Email"], f"You're booked: {d['short_day']}, {d['window']} · code {d['code']}", text, page)
    message.get_payload()[1].add_related(qr_png(d["code"]), maintype="image", subtype="png", cid=qr_cid,
                                         filename="check-in-code.png")
    message.add_attachment(ics(r, manage).encode(), maintype="text", subtype="calendar",
                           filename="rockwall-booking.ics", params={"method": "PUBLISH"})
    return message


def build_cancellation(r):
    d = describe(r)
    struck = {k: f'<s style="color:{MUTED}">{html.escape(d[k])}</s>' for k in ("day", "window", "code")}
    body = f"""
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 24px">
{_row('Climber', html.escape(d['name']))}
{_row('Date', struck['day'])}
{_row('Time', struck['window'])}
{_row('Code', struck['code'])}
</table>
<p style="margin:0 0 20px;font:400 15px/1.55 {FONT};color:{INK}">Thanks for letting us know. Your online space has been released for another climber.</p>
{_button(public_url(), 'Book another time')}"""
    page = _layout(f"Your {d['short_day']} climb is cancelled.", "Booking cancelled",
                   _nowrap(d["day"], d["window"]), body, accent=PURPLE_DARK)
    text = (f"Your TTU Rockwall booking is cancelled.\n\nClimber: {d['name']}\nDate:    {d['day']}\nTime:    {d['window']}\n"
            f"Code:    {d['code']} (no longer valid)\n\nBook another time: {public_url()}\n")
    return _envelope(r["Email"], f"Cancelled: your {d['short_day']} climb", text, page)


def _envelope(to, subject, text, page):
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = subject, sender(), to
    message["Message-ID"] = make_msgid(domain="tntechclimb")
    message.set_content(text)
    message.add_alternative(page, subtype="html")
    # The HTML part becomes multipart/related so the QR can be attached inline.
    message.get_payload()[1].make_related()
    return message


def queue_email(db, kind, reservation, message):
    db.execute("""INSERT INTO email_outbox(kind,reservation_id,to_addr,subject,message,created_at)
      VALUES (?,?,?,?,?,?)""", (kind, reservation["UniqueID"], message["To"], message["Subject"], message.as_bytes(), now_utc()))


def _deliver(message_bytes, row):
    host = os.environ.get("ROCKWALL_SMTP_HOST")
    if not host:
        outbox = database_path().parent / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        (outbox / f"{row['id']:05d}-{row['kind']}.eml").write_bytes(message_bytes)
        return "saved"
    security = os.environ.get("ROCKWALL_SMTP_SECURITY", "starttls").lower()
    port = int(os.environ.get("ROCKWALL_SMTP_PORT", "465" if security == "ssl" else "587"))
    client = smtplib.SMTP_SSL(host, port, timeout=20) if security == "ssl" else smtplib.SMTP(host, port, timeout=20)
    with client:
        if security == "starttls":
            client.starttls()
        if os.environ.get("ROCKWALL_SMTP_USER"):
            client.login(os.environ["ROCKWALL_SMTP_USER"], os.environ.get("ROCKWALL_SMTP_PASSWORD", ""))
        client.sendmail(sender(), [row["to_addr"]], message_bytes)
    return "sent"


def deliver_pending(limit=20):
    """Send queued emails. Each row is claimed first, so overlapping runs never double-send."""
    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    with db_session(write=True) as db:
        db.execute("UPDATE email_outbox SET status='pending' WHERE status='sending' AND last_attempt_at<?", (stale,))
        ids = [r[0] for r in db.execute("SELECT id FROM email_outbox WHERE status='pending' ORDER BY id LIMIT ?", (limit,))]
    results = {"sent": 0, "saved": 0, "failed": 0}
    for outbox_id in ids:
        with db_session(write=True) as db:
            claimed = db.execute("""UPDATE email_outbox SET status='sending',attempts=attempts+1,last_attempt_at=?
              WHERE id=? AND status='pending'""", (now_utc(), outbox_id)).rowcount
            row = db.execute("SELECT * FROM email_outbox WHERE id=?", (outbox_id,)).fetchone()
        if not claimed:
            continue
        try:
            status = _deliver(row["message"], row)
            with db_session(write=True) as db:
                db.execute("UPDATE email_outbox SET status=?,sent_at=?,message=NULL,last_error=NULL WHERE id=?",
                           (status, now_utc(), outbox_id))
            results[status] += 1
        except Exception as error:
            final = row["attempts"] >= MAX_ATTEMPTS
            with db_session(write=True) as db:
                db.execute("UPDATE email_outbox SET status=?,last_error=? WHERE id=?",
                           ("failed" if final else "pending", str(error)[:500], outbox_id))
            results["failed"] += final
    return results

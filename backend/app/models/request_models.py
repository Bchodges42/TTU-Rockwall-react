import re
from typing import Optional, Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ponytail: static denylist, not an ML filter — sized for the bored-student-worker
# threat; determined actors can leetspeak past any static list. Escalate to a
# moderation API only if that ever becomes a real problem.
PROFANITY_RE = re.compile(
    r"\b(?:f[u\*@]ck\w*|sh[i1!*]t\w*|b[i1!*]tch\w*|c[u\*]nts?\w*|p[u\*]ss\s*y\w*|"
    r"n[i1!|]gg\w*|f[a4@]g+(?:[o0i1!?]t)?\w*|wh[o0]res?|sl[u\*]ts?|c[o0]cks?|d[i1!|]cks?|"
    r"bastards?|jackasses?|d[a4@]mn\w*|dumb[ -]?[a4@][s5@$]+|[a4@][s5@$]{2,}(?:h[o0]les?|s)?|"
    # (?!\w) instead of \b at the end: matches may end in symbols ($$), where \b never fires
    r"h[e3]ll)(?!\w)",
    re.IGNORECASE,
)
# High-signal cores only, used on separator-stripped text where word boundaries are gone
# (stripping turns "grass shirts" into "grasshirts"; cores like 'fuck' can't false-positive that way).
PROFANITY_CORE_RE = re.compile(
    r"(?:fuck|sh[i1!*]t|b[i1!*]tch|c[u\*]nt|p[u\*]ssy|n[i1!|]gg|f[a4@]ggo?[i1!]?t|wh[o0]re|sl[u\*]t|c[o0]ck|d[i1!|]ck|jackass|dumb[a4@][s5@$]+)",
    re.IGNORECASE,
)

def ensure_no_profanity(text: str):
    """Raise 400 if text trips the denylist — checks raw text, then a separator-stripped
    form to catch spaced-out evasions like 'f u c k'. The stripped pass uses only
    high-signal cores because stripping concatenates neighboring words."""
    m = PROFANITY_RE.search(text)
    if not m:
        flat = re.sub(r"[^a-z0-9$@*]+", "", text.lower())
        m = PROFANITY_CORE_RE.search(flat)
    if m:
        raise HTTPException(400, f"Inappropriate language isn't allowed (matched \"{m.group(0)}\").")

class Register(BaseModel):
    model_config = ConfigDict(extra="forbid")
    firstname: str = Field(min_length=1, max_length=100)
    lastname: str = Field(min_length=1, max_length=100)
    phone: str = Field(default="", max_length=50)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value
class Login(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)
EMAIL_RE = re.compile(r"[^\s@,;<>\"]+@[^\s@,;<>\"]+\.[^\s@,;<>\"]+")
CLOCK = r"^\d{2}:\d{2}$"
class Appointment(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, max_length=254)
    date: str
    time: str = Field(pattern=CLOCK)  # arrival, local wall time
    departure: Optional[str] = Field(default=None, pattern=CLOCK)  # defaults to one hour after arrival

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = (value or "").strip().lower() or None
        if value and not EMAIL_RE.fullmatch(value):
            raise ValueError("Enter a valid email address")
        return value
class AppointmentPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    date: Optional[str] = None
    time: Optional[str] = Field(default=None, pattern=CLOCK)
    departure: Optional[str] = Field(default=None, pattern=CLOCK)
    status: Optional[Literal["pending","confirmed","cancelled","completed","no-show"]] = None
class CancelByToken(BaseModel):
    token: str = Field(min_length=20, max_length=200)
class CheckIn(BaseModel):
    code: str = Field(min_length=1, max_length=300)  # typed, or the full text a QR scanner sends
class DayHours(BaseModel):
    weekday: int = Field(ge=0, le=6)
    opens: Optional[str] = Field(default=None, pattern=CLOCK)
    closes: Optional[str] = Field(default=None, pattern=CLOCK)

    @model_validator(mode="after")
    def consistent(self):
        if (self.opens is None) != (self.closes is None):
            raise ValueError("Give both opening and closing times, or neither for a closed day")
        if self.opens and (self.opens >= self.closes or self.opens[3:] not in ("00", "30") or self.closes[3:] not in ("00", "30")):
            raise ValueError("Hours must be on the half hour and close after they open")
        return self
class HoursUpdate(BaseModel):
    weekly: Optional[list[DayHours]] = Field(default=None, min_length=7, max_length=7)
    auto_sync: Optional[bool] = None
class ClosureIn(BaseModel):
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    reason: str = Field(default="Closed", max_length=120)
class FeedbackIn(BaseModel):
    route: str; rating: int; comment: str; author: Optional[str] = None

    @model_validator(mode="after")
    def clean(self):
        ensure_no_profanity(self.comment)
        if self.author:
            ensure_no_profanity(self.author)
        return self
class FaqIn(BaseModel):
    q: str; a: str
class CapacityIn(BaseModel):
    max: int = Field(ge=1, le=200)
    online: Optional[int] = Field(default=None, ge=0, le=200)
class EventIn(BaseModel):
    name: str; spots_total: int = 20; spots_filled: int = 0; next_date: str = ""; link: str = ""
class EventPatch(BaseModel):
    name: Optional[str] = None; spots_total: Optional[int] = None; spots_filled: Optional[int] = None; next_date: Optional[str] = None; link: Optional[str] = None
class QueueEntry(BaseModel):
    receipt: Optional[str] = Field(default=None, max_length=100)
    firstname: str = Field(default="Guest", max_length=100)
    lastname: str = Field(default="", max_length=100)
class QueueAction(BaseModel):
    action: Literal["admit","checkout","cancel"]
class SiteContentIn(BaseModel):
    k: str; v: str

    @model_validator(mode="after")
    def clean(self):
        for field in ("k", "v"):
            ensure_no_profanity(getattr(self, field))
        return self

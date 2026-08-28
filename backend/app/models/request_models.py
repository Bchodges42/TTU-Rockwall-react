import re
from typing import Optional
from fastapi import HTTPException
from pydantic import BaseModel, model_validator

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
    firstname: str; lastname: str; phone: str; email: str; password: str
class Login(BaseModel):
    email: str; password: str
class Appointment(BaseModel):
    name: str; date: str; time: str
class AppointmentPatch(BaseModel):
    name: Optional[str] = None; date: Optional[str] = None; time: Optional[str] = None; status: Optional[str] = None
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
    max: int
class EventIn(BaseModel):
    name: str; spots_total: int = 20; spots_filled: int = 0; next_date: str = ""; link: str = ""
class EventPatch(BaseModel):
    name: Optional[str] = None; spots_total: Optional[int] = None; spots_filled: Optional[int] = None; next_date: Optional[str] = None; link: Optional[str] = None
class SiteContentIn(BaseModel):
    k: str; v: str

    @model_validator(mode="after")
    def clean(self):
        for field in ("k", "v"):
            ensure_no_profanity(getattr(self, field))
        return self

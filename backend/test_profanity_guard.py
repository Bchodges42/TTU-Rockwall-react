"""Self-check: profanity guard on SiteContentIn + admin FAQ route."""
import sys
from fastapi import HTTPException

from backend.app.models.request_models import SiteContentIn, ensure_no_profanity


def expect_reject(text, label):
    try:
        SiteContentIn(k="site_title", v=text)
        print(f"FAIL ({label}): accepted {text!r}"); sys.exit(1)
    except HTTPException as e:
        assert e.status_code == 400, f"expected 400, got {e.status_code}"

def expect_accept(text):
    SiteContentIn(k="site_title", v=text)  # raises HTTPException if blocked

# blocked in site titles/values
expect_reject("Shit wall", "curse")
expect_reject("Where campus learns to f u c k", "spaced-out")
expect_reject("Climb your a$$ off", "leetspeak $")
expect_reject("B!TCHIN holds", "leetspeak !")
expect_reject("you're all 4ssh0les", "leetspeak digits")
# legit copy must pass (Scunthorpe-safe)
expect_accept("TTU Rockwall")
expect_accept("Campus Recreation · Climbing Wall")
expect_accept("Where campus learns to climb.")
expect_accept("3 PM – 8 PM")
expect_accept("Assateague Island climbing trip — sign up Friday")
expect_accept("Class is full, so climb at your own pace")

# key field guarded too
try:
    SiteContentIn(k="f u c k", v="x"); print("FAIL: key not guarded"); sys.exit(1)
except HTTPException:
    pass

# FAQ query-param path shares the same denylist
for bad in ("What the hell are hours?", "dumb a s s question"):
    try:
        ensure_no_profanity(bad); print(f"FAIL: FAQ accepted {bad!r}"); sys.exit(1)
    except HTTPException as e:
        assert e.status_code == 400

print("profanity-guard checks passed")

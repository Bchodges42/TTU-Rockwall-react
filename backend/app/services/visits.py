"""Visit lifecycle and scheduled housekeeping, independent of browser sessions."""
from datetime import datetime
from .database_service import db_session
from .time_service import booking_time, now_utc, wall_zone


def enqueue_due(db, stamp=None):
    stamp = stamp or now_utc()
    local_day = datetime.fromisoformat(stamp).astimezone(wall_zone()).date().isoformat()
    db.execute("""INSERT INTO visitorsInQueue(UniqueID_SignedUp,Arrival_Time_SignUp)
      SELECT r.UniqueID,r.Arrival_Time FROM visitorsSignedUp r
      WHERE r.Status='confirmed' AND r.Arrival_Time>=? AND r.Arrival_Time<=?
      AND NOT EXISTS (SELECT 1 FROM visitorsInQueue q WHERE q.UniqueID_SignedUp=r.UniqueID)""",
      (booking_time(local_day, "00:00"), stamp))


def cleanup_database(stamp=None):
    stamp = stamp or now_utc()
    local_day = datetime.fromisoformat(stamp).astimezone(wall_zone()).date().isoformat()
    midnight = booking_time(local_day, "00:00")
    with db_session(write=True) as db:
        enqueue_due(db, stamp)
        db.execute("DELETE FROM sessions WHERE expires_at<=?", (stamp,))
        # Preserve aggregate peak counts and anyone still physically checked in.
        db.execute("""DELETE FROM visitorsInQueue WHERE "UniqueID_Walk-in" IN
          (SELECT UniqueID FROM visitorsWalkIn WHERE Arrival_Time<?) AND Status<>'admitted'""", (midnight,))
        removed = db.execute("""DELETE FROM visitorsWalkIn WHERE Arrival_Time<?
          AND NOT EXISTS (SELECT 1 FROM visitorsInQueue q WHERE q."UniqueID_Walk-in"=visitorsWalkIn.UniqueID)""",
          (midnight,)).rowcount
        db.execute("""UPDATE visitorsSignedUp SET Status='no-show',UpdatedAt=?
          WHERE Arrival_Time<? AND Status IN ('pending','confirmed')
          AND NOT EXISTS (SELECT 1 FROM visitorsInQueue q WHERE q.UniqueID_SignedUp=visitorsSignedUp.UniqueID
            AND q.Status='admitted')""", (stamp, midnight))
        db.execute("""UPDATE visitorsInQueue SET Status='cancelled'
          WHERE Status='waiting' AND UniqueID_SignedUp IN
          (SELECT UniqueID FROM visitorsSignedUp WHERE Status='no-show')""")
    return {"walkins_removed": removed}

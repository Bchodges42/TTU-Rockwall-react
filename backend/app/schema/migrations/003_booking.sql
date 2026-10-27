-- Booking window, pickup codes, email cancellation and operating hours.
-- Applied once after 002_jonah; Jonah's columns are untouched, only new ones are added.

-- Visitors pick an arrival and a departure; legacy rows are backfilled to arrival + 1 hour.
ALTER TABLE visitorsSignedUp ADD COLUMN Departure_Time TEXT;
-- Short code shown at the desk (fast-food style). Unique among bookings that are still active,
-- so a code can be reused once a visit is over.
ALTER TABLE visitorsSignedUp ADD COLUMN PickupCode TEXT;
-- Where the confirmation and cancellation emails go.
ALTER TABLE visitorsSignedUp ADD COLUMN Email TEXT;
-- SHA-256 of the secret in the email's "manage booking" link; the link itself is never stored.
ALTER TABLE visitorsSignedUp ADD COLUMN CancelTokenHash TEXT;
CREATE UNIQUE INDEX reservations_active_code ON visitorsSignedUp(PickupCode)
  WHERE PickupCode IS NOT NULL AND Status IN ('pending','confirmed');
CREATE UNIQUE INDEX reservations_cancel_token ON visitorsSignedUp(CancelTokenHash)
  WHERE CancelTokenHash IS NOT NULL;
CREATE INDEX reservations_account ON visitorsSignedUp(AccountID, Arrival_Time);

-- Weekly climbing-wall hours (0 = Monday). NULL opens/closes = closed that day.
-- Kept in sync with tntech.edu/recreation/hours.php unless an admin turns auto-sync off.
CREATE TABLE operating_hours (
  weekday INTEGER PRIMARY KEY CHECK (weekday BETWEEN 0 AND 6),
  opens TEXT,
  closes TEXT,
  CHECK ((opens IS NULL) = (closes IS NULL)),
  CHECK (opens IS NULL OR opens < closes)
);
-- Fall 2026 hours from the TTU page, so a fresh install works before the first sync.
INSERT INTO operating_hours VALUES
  (0,'14:00','19:00'), (1,'14:00','19:00'), (2,'14:00','19:00'), (3,'14:00','19:00'),
  (4,NULL,NULL), (5,NULL,NULL), (6,NULL,NULL);

-- One-off closures (holidays, maintenance) that override the weekly hours.
CREATE TABLE closures (
  day TEXT PRIMARY KEY,
  reason TEXT NOT NULL DEFAULT ''
);

-- Outgoing email, written in the same transaction as the booking change and sent afterwards
-- (with retries) so a slow or down mail server never blocks or loses a booking.
-- The message body is cleared once sent because it contains the manage-booking link.
CREATE TABLE email_outbox (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  reservation_id INTEGER REFERENCES visitorsSignedUp(UniqueID) ON DELETE SET NULL,
  to_addr TEXT NOT NULL,
  subject TEXT NOT NULL,
  message BLOB,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sending','sent','saved','failed')),
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  last_attempt_at TEXT,
  sent_at TEXT
);
CREATE INDEX email_outbox_pending ON email_outbox(status, id);

-- Online bookings are capped below the wall's maximum so walk-ins still have room.
INSERT OR IGNORE INTO settings(k,v) VALUES ('online_capacity','10');
-- How many days ahead the booking window reaches.
INSERT OR IGNORE INTO settings(k,v) VALUES ('booking_days','7');
INSERT OR IGNORE INTO settings(k,v) VALUES ('hours_auto_sync','1');
INSERT OR IGNORE INTO settings(k,v) VALUES ('hours_synced_at','');
INSERT OR IGNORE INTO settings(k,v) VALUES ('hours_sync_status','Not synced yet; using Fall 2026 hours.');

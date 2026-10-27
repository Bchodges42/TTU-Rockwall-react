-- Jonah Irwin's five core table names and original identifiers are preserved.
-- PasswordHash replaces the prototype's plaintext TEMPPASSWORD.
CREATE TABLE tableSignInInfo (
  UniqueID INTEGER PRIMARY KEY,
  Username TEXT NOT NULL COLLATE NOCASE UNIQUE,
  PasswordHash TEXT NOT NULL,
  LastName TEXT NOT NULL,
  FirstName TEXT NOT NULL,
  UserPhone TEXT,
  UserEmail TEXT COLLATE NOCASE UNIQUE,
  IsActive INTEGER NOT NULL DEFAULT 1 CHECK (IsActive IN (0,1)),
  CreatedAt TEXT NOT NULL
);
CREATE TABLE tableTrustedUsers (
  UniqueID INTEGER PRIMARY KEY REFERENCES tableSignInInfo(UniqueID),
  LastName TEXT NOT NULL,
  FirstName TEXT NOT NULL,
  "Moderator?" INTEGER NOT NULL DEFAULT 0 CHECK ("Moderator?" IN (0,1)),
  "Super-Moderator?" INTEGER NOT NULL DEFAULT 0 CHECK ("Super-Moderator?" IN (0,1)),
  "Most_recent_clock-in" TEXT
);
CREATE TABLE visitorsSignedUp (
  UniqueID INTEGER PRIMARY KEY,
  AccountID INTEGER REFERENCES tableSignInInfo(UniqueID),
  Username TEXT NOT NULL,
  LastName TEXT NOT NULL,
  FirstName TEXT NOT NULL,
  Arrival_Time TEXT NOT NULL,
  ReceiptCode TEXT NOT NULL UNIQUE,
  Status TEXT NOT NULL DEFAULT 'confirmed' CHECK (Status IN ('pending','confirmed','cancelled','completed','no-show')),
  CreatedAt TEXT NOT NULL,
  UpdatedAt TEXT NOT NULL
);
CREATE INDEX reservations_arrival ON visitorsSignedUp(Arrival_Time,Status);
CREATE TABLE visitorsWalkIn (
  UniqueID INTEGER PRIMARY KEY,
  LastName TEXT NOT NULL,
  FirstName TEXT NOT NULL,
  Arrival_Time TEXT NOT NULL
);
CREATE TABLE visitorsInQueue (
  QueueID INTEGER PRIMARY KEY,
  UniqueID_SignedUp INTEGER REFERENCES visitorsSignedUp(UniqueID),
  "UniqueID_Walk-in" INTEGER REFERENCES visitorsWalkIn(UniqueID),
  Arrival_Time_SignUp TEXT,
  "Arrival_Time_Walk-in" TEXT,
  Status TEXT NOT NULL DEFAULT 'waiting' CHECK (Status IN ('waiting','admitted','completed','cancelled')),
  CheckedInAt TEXT,
  CheckedOutAt TEXT,
  CHECK ((UniqueID_SignedUp IS NOT NULL) + ("UniqueID_Walk-in" IS NOT NULL) = 1),
  CHECK ((Status = 'admitted' AND CheckedInAt IS NOT NULL AND CheckedOutAt IS NULL)
      OR (Status = 'completed' AND CheckedInAt IS NOT NULL AND CheckedOutAt IS NOT NULL)
      OR (Status IN ('waiting','cancelled') AND CheckedInAt IS NULL AND CheckedOutAt IS NULL))
);
CREATE UNIQUE INDEX queue_unique_reservation ON visitorsInQueue(UniqueID_SignedUp)
  WHERE Status IN ('waiting','admitted');
CREATE UNIQUE INDEX queue_unique_walkin ON visitorsInQueue("UniqueID_Walk-in")
  WHERE Status IN ('waiting','admitted');
-- Existing website features, independent of the visitor-management core.
CREATE TABLE IF NOT EXISTS feedback (id TEXT PRIMARY KEY, route TEXT, rating INTEGER, comment TEXT, author TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS faqs (id INTEGER PRIMARY KEY AUTOINCREMENT, q TEXT, a TEXT);
CREATE TABLE IF NOT EXISTS equipment (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, status TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS peak_visits (hour INTEGER, count INTEGER);
CREATE TABLE IF NOT EXISTS leaderboard (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, score INTEGER);
CREATE TABLE IF NOT EXISTS routes (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, grade TEXT, setter TEXT);
CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, spots_total INTEGER, spots_filled INTEGER, next_date TEXT, link TEXT);
CREATE TABLE IF NOT EXISTS site_content (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE sessions (
  token_hash TEXT PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES tableSignInInfo(UniqueID) ON DELETE CASCADE,
  expires_at TEXT NOT NULL
);
CREATE TABLE migration_issues (
  id INTEGER PRIMARY KEY,
  source_table TEXT NOT NULL,
  record_id TEXT,
  reason TEXT NOT NULL,
  record_json TEXT NOT NULL
);
INSERT OR IGNORE INTO settings(k,v) VALUES ('capacity_max','20');
INSERT OR IGNORE INTO settings(k,v) VALUES ('guest_sequence','0');
INSERT OR IGNORE INTO site_content(k,v) VALUES ('site_title','TTU Rockwall');
INSERT OR IGNORE INTO site_content(k,v) VALUES ('site_kicker','Campus Recreation · Climbing Wall');
INSERT OR IGNORE INTO site_content(k,v) VALUES ('hero_title','Where campus learns to climb.');
INSERT OR IGNORE INTO site_content(k,v) VALUES ('hours_today','3 PM – 8 PM');

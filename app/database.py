import aiosqlite
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "./scheduler.db")

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS candidates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    email       TEXT    NOT NULL UNIQUE,
    phone       TEXT,
    role        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'applied',
    notes       TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT    PRIMARY KEY,
    candidate_id  INTEGER NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'active',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (candidate_id) REFERENCES candidates(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    role        TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS interview_slots (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       TEXT    NOT NULL,
    candidate_id     INTEGER NOT NULL,
    scheduled_time   DATETIME NOT NULL,
    duration_minutes INTEGER  DEFAULT 45,
    location         TEXT     DEFAULT 'Google Meet link will be sent via email',
    status           TEXT     NOT NULL DEFAULT 'confirmed',
    notes            TEXT,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id)   REFERENCES sessions(id),
    FOREIGN KEY (candidate_id) REFERENCES candidates(id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id  INTEGER NOT NULL,
    type          TEXT    NOT NULL DEFAULT 'email',
    subject       TEXT    NOT NULL,
    body          TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'pending',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (candidate_id) REFERENCES candidates(id)
);

CREATE TABLE IF NOT EXISTS activity_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT    NOT NULL,
    entity_type TEXT    NOT NULL,
    entity_id   INTEGER,
    details     TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_sessions_candidate ON sessions(candidate_id);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_slots_candidate ON interview_slots(candidate_id);
CREATE INDEX IF NOT EXISTS idx_slots_time ON interview_slots(scheduled_time);
CREATE INDEX IF NOT EXISTS idx_notifications_candidate ON notifications(candidate_id);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);
"""

DEFAULT_SETTINGS = {
    "company_name": "TechCorp",
    "recruiter_name": "Alex",
    "timezone": "Asia/Kolkata",
    "interview_duration": "45",
    "interview_location": "Google Meet link will be sent via email",
    "buffer_minutes": "15",
    "ai_tone": "friendly",
}


async def get_db():
    """Async context manager for DB connection."""
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db():
    """Create all tables on startup and seed default settings."""
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()

        # Seed default settings if empty
        cur = await db.execute("SELECT COUNT(*) as cnt FROM settings")
        row = await cur.fetchone()
        if row[0] == 0:
            for key, value in DEFAULT_SETTINGS.items():
                await db.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, value),
                )
            await db.commit()


async def log_activity(db, action: str, entity_type: str, entity_id: int = None, details: str = None):
    """Log an activity event."""
    await db.execute(
        "INSERT INTO activity_log (action, entity_type, entity_id, details) VALUES (?, ?, ?, ?)",
        (action, entity_type, entity_id, details),
    )
    await db.commit()

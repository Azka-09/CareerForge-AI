"""SQLite access with versioned, non-destructive migrations.
Every migration is idempotent and only adds structure; nothing is dropped or reset."""
import logging
import sqlite3
from contextlib import contextmanager

from config import DB_PATH

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """User-safe database failure (details are logged, not shown)."""


_BASELINE = """
CREATE TABLE IF NOT EXISTS analyses(
  id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, resume_name TEXT,
  job_title TEXT, kind TEXT, result_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS resume_versions(
  id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, name TEXT, content_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS interview_sessions(
  id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, job_title TEXT, company TEXT, category TEXT,
  difficulty TEXT, num_questions INTEGER, status TEXT DEFAULT 'in_progress',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS interview_questions(
  id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, interview_id INTEGER NOT NULL, idx INTEGER NOT NULL,
  category TEXT, question TEXT, answer TEXT, evaluation_json TEXT, UNIQUE(interview_id, idx));
CREATE TABLE IF NOT EXISTS roadmaps(
  id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, job_title TEXT, roadmap_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS roadmap_tasks(
  session_id TEXT NOT NULL, roadmap_id INTEGER NOT NULL, task_key TEXT NOT NULL, done INTEGER DEFAULT 0,
  PRIMARY KEY(roadmap_id, task_key));
CREATE TABLE IF NOT EXISTS applications(
  id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, company TEXT, job_title TEXT,
  status TEXT DEFAULT 'Interested', applied_on TEXT, interview_on TEXT, notes TEXT);
"""


def _m1_baseline(con):
    con.executescript(_BASELINE)


def _m2_interview_columns(con):
    """Phase 1 databases have a narrower interview_sessions table; add columns in place."""
    have = {r[1] for r in con.execute("PRAGMA table_info(interview_sessions)")}
    for col, typ in (("company", "TEXT"), ("category", "TEXT"), ("difficulty", "TEXT"),
                     ("num_questions", "INTEGER"), ("status", "TEXT DEFAULT 'in_progress'")):
        if col not in have:
            con.execute(f"ALTER TABLE interview_sessions ADD COLUMN {col} {typ}")


def _m3_auth(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
      failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS auth_sessions(
      token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      expires_at TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    """)


def _m4_usage_and_indexes(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS ai_usage(
      owner TEXT NOT NULL, day TEXT NOT NULL, calls INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(owner, day));
    CREATE INDEX IF NOT EXISTS idx_analyses_owner ON analyses(session_id);
    CREATE INDEX IF NOT EXISTS idx_versions_owner ON resume_versions(session_id);
    CREATE INDEX IF NOT EXISTS idx_interviews_owner ON interview_sessions(session_id);
    CREATE INDEX IF NOT EXISTS idx_iq_owner ON interview_questions(session_id, interview_id);
    CREATE INDEX IF NOT EXISTS idx_roadmaps_owner ON roadmaps(session_id);
    CREATE INDEX IF NOT EXISTS idx_rtasks_owner ON roadmap_tasks(session_id, roadmap_id);
    CREATE INDEX IF NOT EXISTS idx_apps_owner ON applications(session_id);
    CREATE INDEX IF NOT EXISTS idx_authsess_user ON auth_sessions(user_id);
    """)


MIGRATIONS = [(1, "baseline", _m1_baseline), (2, "interview_columns", _m2_interview_columns),
              (3, "auth_tables", _m3_auth), (4, "usage_and_indexes", _m4_usage_and_indexes)]


def migrate(con) -> list[int]:
    """Apply pending migrations in order. Returns the versions applied now."""
    con.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, name TEXT, "
                "applied_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    done = {r[0] for r in con.execute("SELECT version FROM schema_migrations")}
    applied = []
    for version, name, fn in MIGRATIONS:
        if version not in done:
            fn(con)
            con.execute("INSERT INTO schema_migrations(version, name) VALUES(?,?)", (version, name))
            con.commit()
            applied.append(version)
            logger.info("Applied database migration %d (%s)", version, name)
    return applied


def schema_version(con) -> int:
    try:
        return con.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()[0]
    except sqlite3.Error:
        return 0


@contextmanager
def connect(path: str | None = None):
    con = sqlite3.connect(path or DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        migrate(con)
        yield con
        con.commit()
    except sqlite3.Error as e:
        con.rollback()
        logger.error("Database error: %s", type(e).__name__)
        raise DatabaseError("A database error occurred. Please try again.") from e
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

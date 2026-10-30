import sys, os, sqlite3, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
import config, health
from database import db as dbm, repository as repo
from services import usage_limiter as ul
from utils.logging_setup import redact, RedactingFormatter


class patched:
    """Temporarily set config attributes (no monkeypatch dependency)."""
    def __init__(s, **kw): s.kw, s.old = kw, {}
    def __enter__(s):
        for k, v in s.kw.items(): s.old[k] = getattr(config, k); setattr(config, k, v)
    def __exit__(s, *a):
        for k, v in s.old.items(): setattr(config, k, v)


# ---------- migrations ----------
def test_fresh_database_is_fully_migrated(tmp_path):
    db = str(tmp_path / "n.db")
    with dbm.connect(db) as con:
        assert dbm.schema_version(con) == dbm.MIGRATIONS[-1][0]
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "auth_sessions", "ai_usage", "schema_migrations", "interview_questions"} <= tables


def test_migrations_are_idempotent_and_preserve_existing_data(tmp_path):
    db = str(tmp_path / "old.db"); c = sqlite3.connect(db)          # a Phase 1 database with real rows
    c.execute("CREATE TABLE interview_sessions(id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, job_title TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE analyses(id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, resume_name TEXT, job_title TEXT, kind TEXT, result_json TEXT, created_at TEXT)")
    c.execute("INSERT INTO interview_sessions(session_id, job_title) VALUES('A','Old job')")
    c.execute("INSERT INTO analyses(session_id, resume_name) VALUES('A','cv.pdf')"); c.commit(); c.close()
    for _ in range(3):
        with dbm.connect(db) as con:
            assert con.execute("SELECT job_title FROM interview_sessions").fetchone()[0] == "Old job"
            assert con.execute("SELECT resume_name FROM analyses").fetchone()[0] == "cv.pdf"
            assert con.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == len(dbm.MIGRATIONS)


def test_indexes_exist_and_foreign_keys_enforced(tmp_path):
    db = str(tmp_path / "n.db")
    with dbm.connect(db) as con:
        idx = {r[1] for r in con.execute("PRAGMA index_list(interview_questions)")}
        assert "idx_iq_owner" in idx
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES('h',999,'x')")


def test_database_errors_are_wrapped_and_rolled_back(tmp_path):
    db = str(tmp_path / "n.db")
    with pytest.raises(dbm.DatabaseError):
        with dbm.connect(db) as con:
            con.execute("INSERT INTO users(email,password_hash) VALUES('a','h')")
            con.execute("INSERT INTO users(email,password_hash) VALUES('a','h')")   # UNIQUE violation
    with dbm.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0          # first insert rolled back


def test_unreadable_database_gives_safe_error(tmp_path):
    bad = tmp_path / "bad.db"; bad.write_bytes(b"this is not a sqlite database" * 50)
    with pytest.raises(dbm.DatabaseError) as e:
        with dbm.connect(str(bad)): pass
    assert str(tmp_path) not in str(e.value)                 # no filesystem path leaked


# ---------- AI usage limits ----------
def test_daily_limit_enforced_per_user_and_day(tmp_path):
    db = str(tmp_path / "u.db"); day = "2026-10-30"
    assert [ul.consume("uA", 3, db, day) for _ in range(5)] == [True, True, True, False, False]
    assert ul.used_today("uA", db, day) == 3
    assert ul.consume("uB", 3, db, day) is True                    # other user unaffected
    assert ul.consume("uA", 3, db, "2026-10-31") is True           # new day resets
    assert all(ul.consume("uC", 0, db, day) for _ in range(10))    # 0 = unlimited


def test_deleting_data_does_not_reset_quota(tmp_path):
    db = str(tmp_path / "u.db"); day = ul._today()
    ul.consume("uA", 1, db, day); repo.delete_all("uA", db)
    assert ul.consume("uA", 1, db, day) is False


# ---------- config validation ----------
def test_validate_default_is_ok_with_warnings():
    with patched(DATABASE_URL="sqlite:///x.db", APP_ENV="development", LLM_API_KEY=""):
        errors, warnings = config.validate()
    assert errors == [] and any("OPENAI_API_KEY" in w for w in warnings)


def test_validate_reports_bad_settings_without_leaking_secrets():
    with patched(DATABASE_URL="postgresql://u:supersecret@h/db", APP_ENV="staging", EMBEDDING_PROVIDER="x",
                 RAG_CHUNK_OVERLAP=900, LLM_API_KEY="sk-live-SECRETVALUE123"):
        errors, warnings = config.validate()
    text = " ".join(errors + warnings)
    assert len(errors) >= 4 and "supersecret" not in text and "SECRETVALUE" not in text


# ---------- logging redaction ----------
def test_redaction():
    s = redact("key sk-abc123DEF456ghi789 mail bob@example.com password=hunter2 token: abc.def")
    for leaked in ("sk-abc123", "bob@example.com", "hunter2", "abc.def"): assert leaked not in s


def test_formatter_redacts_tracebacks():
    try: raise ValueError("bad key sk-abc123DEF456ghi789")
    except ValueError:
        rec = logging.LogRecord("t", logging.ERROR, "f", 1, "failed", None, sys.exc_info())
    assert "sk-abc123" not in RedactingFormatter("%(message)s").format(rec)


# ---------- health ----------
def test_health_ok_and_failure(tmp_path):
    with patched(DATABASE_URL="sqlite:///x.db"):
        assert health.check(str(tmp_path / "h.db"))["status"] == "ok"
    bad = tmp_path / "bad.db"; bad.write_bytes(b"garbage" * 100)
    r = health.check(str(bad))
    assert r["status"] == "error" and r["checks"]["database"]["ok"] is False

import sys, os, sqlite3
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from services import auth_service as auth
from database import repository as repo


PW = "correct-horse-battery-9"
EV = {"score": 7, "strengths": [], "weaknesses": [], "missing_points": [], "recommendations": [],
      "suggested_structure": "", "improved_example": "", "claims_to_verify": []}


def two_users(tmp_path):
    db = str(tmp_path / "t.db")
    a = auth.register("alice@example.com", PW, db); b = auth.register("bob@example.com", PW, db)
    return db, auth.owner_key(a["id"]), auth.owner_key(b["id"]), a, b


# ---------- registration & passwords ----------
def test_password_never_stored_in_plain_text(tmp_path):
    db = str(tmp_path / "t.db"); auth.register("a@example.com", PW, db)
    raw = sqlite3.connect(db).execute("SELECT password_hash FROM users").fetchone()[0]
    assert PW not in raw and (raw.startswith("scrypt$") or raw.startswith("$argon2"))


def test_same_password_gets_different_hashes():
    assert auth.hash_password(PW) != auth.hash_password(PW)
    assert auth.verify_password(PW, auth.hash_password(PW)) and not auth.verify_password("wrong-password-1", auth.hash_password(PW))


def test_verify_rejects_garbage_hashes():
    for bad in ("", "plaintext", "scrypt$bad", "scrypt$1$1$1$!!$!!", "$argon2id$garbage"):
        assert auth.verify_password(PW, bad) is False


def test_password_policy():
    for bad in ("short1", "alllettersonlyhere", "123456789012345", "password1234", "alicebob-secret1"):
        with pytest.raises(auth.AuthError):
            auth.validate_password(bad, "alicebob@example.com")
    auth.validate_password(PW)


def test_email_validation_and_duplicates(tmp_path):
    db = str(tmp_path / "t.db")
    for bad in ("", "nope", "a@b", "a b@c.com", "x" * 260 + "@a.com"):
        with pytest.raises(auth.AuthError): auth.register(bad, PW, db)
    auth.register("Dup@Example.com", PW, db)
    with pytest.raises(auth.AuthError): auth.register("dup@example.com", PW, db)   # case-insensitive


# ---------- login / sessions ----------
def test_login_success_and_generic_failures(tmp_path):
    db, *_ = two_users(tmp_path)
    token, user = auth.login("ALICE@example.com", PW, db)
    assert user["email"] == "alice@example.com" and auth.validate_session(token, db)["id"] == user["id"]
    msgs = set()
    for e, p in (("alice@example.com", "wrong-password-99"), ("ghost@example.com", PW), ("not-an-email", PW)):
        try: auth.login(e, p, db)
        except auth.AuthError as ex: msgs.add(str(ex))
    assert msgs == {"Invalid email or password."}            # no user enumeration


def test_new_token_every_login_and_tokens_stored_hashed(tmp_path):
    db, *_ = two_users(tmp_path)
    t1, _ = auth.login("alice@example.com", PW, db); t2, _ = auth.login("alice@example.com", PW, db)
    assert t1 != t2
    stored = [r[0] for r in sqlite3.connect(db).execute("SELECT token_hash FROM auth_sessions")]
    assert t1 not in stored and t2 not in stored and len(stored) == 2


def test_invalid_tampered_and_expired_sessions(tmp_path):
    db, *_ = two_users(tmp_path)
    now = datetime.now(timezone.utc)
    token, _ = auth.login("alice@example.com", PW, db, now=now)
    for bad in (None, "", "garbage", token + "x", token[:-1], 12345):
        assert auth.validate_session(bad, db) is None
    assert auth.validate_session(token, db, now=now + timedelta(hours=9)) is None      # expired (8h default)
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0   # expired row purged


def test_logout_revokes_session(tmp_path):
    db, *_ = two_users(tmp_path)
    token, _ = auth.login("alice@example.com", PW, db)
    auth.logout(token, db)
    assert auth.validate_session(token, db) is None


def test_lockout_after_repeated_failures_and_recovery(tmp_path):
    db, *_ = two_users(tmp_path); now = datetime.now(timezone.utc)
    for _ in range(auth.MAX_FAILED):
        with pytest.raises(auth.AuthError): auth.login("alice@example.com", "wrong-password-99", db, now=now)
    with pytest.raises(auth.AuthError) as e: auth.login("alice@example.com", PW, db, now=now)   # even correct pw is blocked
    assert "Too many" in str(e.value)
    token, _ = auth.login("alice@example.com", PW, db, now=now + timedelta(minutes=auth.LOCK_MINUTES + 1))
    assert token


# ---------- cross-user authorization (A must never touch B) ----------
def test_cross_user_interviews(tmp_path):
    db, A, B, *_ = two_users(tmp_path)
    iid = repo.create_interview(A, {"job_title": "Eng"}, [{"question": "Secret question A?", "category": "hr"}], db)
    repo.save_answer(A, iid, 0, "private answer", EV, db)
    assert repo.load_interview(B, iid, db) is None                      # cannot read by guessing the id
    assert repo.list_interviews(B, db) == []
    repo.save_answer(B, iid, 0, "HACKED", None, db)                      # cannot modify
    assert repo.load_interview(A, iid, db)["items"][0]["answer"] == "private answer"
    repo.complete_interview(B, iid, db)                                  # cannot change status
    assert repo.load_interview(A, iid, db)["meta"]["status"] == "in_progress"
    assert repo.delete_interview(B, iid, db) is False                    # cannot delete
    assert repo.load_interview(A, iid, db) is not None
    repo.delete_interviews(B, db); repo.delete_all(B, db)                # B's bulk deletes spare A
    assert repo.load_interview(A, iid, db) is not None


def test_cross_user_roadmaps(tmp_path):
    db, A, B, *_ = two_users(tmp_path)
    rid = repo.save_roadmap(A, "Eng", {"skills": []}, db)
    with pytest.raises(PermissionError): repo.set_task(B, rid, "x", True, db)
    assert repo.latest_roadmap(B, db) is None and repo.done_tasks(B, rid, db) == set()
    repo.delete_roadmaps(B, db)
    assert repo.latest_roadmap(A, db) is not None


def test_export_contains_only_own_data(tmp_path):
    db, A, B, *_ = two_users(tmp_path)
    repo.create_interview(A, {"job_title": "A-only-title"}, [{"question": "A-only-question?"}], db)
    repo.save_roadmap(B, "B-title", {}, db)
    ea, eb = repo.export_user(A, db), repo.export_user(B, db)
    assert "A-only-title" in str(ea) and "A-only-title" not in str(eb)
    assert "B-title" in str(eb) and "B-title" not in str(ea)
    assert "password" not in str(ea).lower()


def test_owner_key_cannot_be_forged_from_user_input():
    assert auth.owner_key(7) == "u7"
    with pytest.raises(ValueError): auth.owner_key("7; DROP TABLE users")


def test_sql_injection_in_inputs_is_inert(tmp_path):
    db, A, B, *_ = two_users(tmp_path)
    iid = repo.create_interview(A, {"job_title": "x'); DROP TABLE users;--"}, [{"question": "Q'; DELETE FROM roadmaps;--"}], db)
    with pytest.raises(auth.AuthError): auth.login("a@b.com' OR '1'='1", "x", db)
    assert repo.load_interview(A, iid, db) and len(sqlite3.connect(db).execute("SELECT * FROM users").fetchall()) == 2


# ---------- account deletion ----------
def test_delete_account_removes_everything_for_that_user_only(tmp_path):
    db, A, B, a, b = two_users(tmp_path)
    ta, _ = auth.login("alice@example.com", PW, db); tb, _ = auth.login("bob@example.com", PW, db)
    repo.create_interview(A, {}, [{"question": "Q a?"}], db); repo.create_interview(B, {}, [{"question": "Q b?"}], db)
    rid = repo.save_roadmap(A, "x", {}, db)
    auth.delete_account(a["id"], db)
    assert auth.validate_session(ta, db) is None and auth.validate_session(tb, db)["id"] == b["id"]
    assert repo.list_interviews(A, db) == [] and repo.latest_roadmap(A, db) is None
    assert len(repo.list_interviews(B, db)) == 1
    with pytest.raises(auth.AuthError): auth.login("alice@example.com", PW, db)
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM auth_sessions WHERE user_id=?", (a["id"],)).fetchone()[0] == 0

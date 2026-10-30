"""Authentication: registration, login, server-side sessions, lockout, account deletion.
Passwords: Argon2id (argon2-cffi) when installed, otherwise stdlib scrypt with a random salt.
Session tokens: 256-bit random, only their SHA-256 is stored. No custom cryptography."""
import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

import config
from database.db import connect, DatabaseError
from database import repository

logger = logging.getLogger(__name__)
MAX_FAILED, LOCK_MINUTES = 5, 15
_EMAIL = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
_COMMON = {"password1234", "passw0rd1234", "123456789012", "qwertyuiop12", "letmein12345", "welcome12345"}
_dummy_hash: str | None = None


class AuthError(Exception):
    """Message is safe to show to the user."""


def owner_key(user_id: int) -> str:
    return f"u{int(user_id)}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")


def validate_email(email: str) -> str:
    e = (email or "").strip().lower()
    if len(e) > 254 or not _EMAIL.match(e):
        raise AuthError("Enter a valid email address.")
    return e


def validate_password(password: str, email: str = "") -> None:
    pw = password or ""
    if not 12 <= len(pw) <= 128:
        raise AuthError("Password must be 12 to 128 characters long.")
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)):
        raise AuthError("Password must contain at least one letter and one number.")
    if pw.lower() in _COMMON:
        raise AuthError("That password is too common. Choose another.")
    local = email.split("@")[0].lower()
    if len(local) >= 4 and local in pw.lower():
        raise AuthError("Password must not contain your email name.")


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str) -> str:
    try:
        from argon2 import PasswordHasher
        return PasswordHasher().hash(password)
    except ImportError:
        salt = os.urandom(16)
        dk = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
        return f"scrypt${2 ** 14}$8$1${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("$argon2"):
        try:
            from argon2 import PasswordHasher
            from argon2.exceptions import VerificationError, InvalidHashError
            return PasswordHasher().verify(stored, password)
        except ImportError:
            return False
        except (VerificationError, InvalidHashError):
            return False
    if stored.startswith("scrypt$"):
        try:
            _, n, r, p, salt, dk = stored.split("$")
            want = base64.b64decode(dk)
            got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(want))
            return hmac.compare_digest(got, want)
        except Exception:
            return False
    return False


def register(email: str, password: str, path=None) -> dict:
    email = validate_email(email)
    validate_password(password, email)
    pw_hash = hash_password(password)
    try:
        with connect(path) as con:
            cur = con.execute("INSERT INTO users(email, password_hash) VALUES(?,?)", (email, pw_hash))
            return {"id": cur.lastrowid, "email": email}
    except DatabaseError as e:
        if isinstance(e.__cause__, sqlite3.IntegrityError):
            raise AuthError("An account with this email already exists.") from None
        raise


def _new_session(con, user_id: int, now: datetime) -> str:
    token = secrets.token_urlsafe(32)
    con.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (_iso(now),))
    con.execute("INSERT INTO auth_sessions(token_hash, user_id, expires_at) VALUES(?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), user_id,
                 _iso(now + timedelta(hours=config.AUTH_SESSION_HOURS))))
    return token


def login(email: str, password: str, path=None, now: datetime | None = None) -> tuple[str, dict]:
    """Returns (session_token, user). A fresh token is issued on every login (no session fixation)."""
    global _dummy_hash
    now = now or _now()
    generic = AuthError("Invalid email or password.")
    try:
        email = validate_email(email)
    except AuthError:
        raise generic from None
    with connect(path) as con:
        u = con.execute("SELECT id,password_hash,failed_attempts,locked_until FROM users WHERE email=?", (email,)).fetchone()
        if u is None:
            _dummy_hash = _dummy_hash or hash_password("timing-equalisation-only")
            verify_password(password or "", _dummy_hash)          # keep timing similar for unknown emails
            raise generic
        if u["locked_until"] and u["locked_until"] > _iso(now):
            raise AuthError("Too many failed attempts. Try again in a few minutes.")
        if not verify_password(password or "", u["password_hash"]):
            attempts = u["failed_attempts"] + 1
            lock = _iso(now + timedelta(minutes=LOCK_MINUTES)) if attempts >= MAX_FAILED else None
            con.execute("UPDATE users SET failed_attempts=?, locked_until=? WHERE id=?",
                        (0 if lock else attempts, lock, u["id"]))
            con.commit()
            logger.warning("Failed login for user id %s", u["id"])
            raise generic
        con.execute("UPDATE users SET failed_attempts=0, locked_until=NULL WHERE id=?", (u["id"],))
        return _new_session(con, u["id"], now), {"id": u["id"], "email": email}


def validate_session(token: str | None, path=None, now: datetime | None = None) -> dict | None:
    """Server-side check on every page run. Returns the user or None (unknown/expired/revoked)."""
    if not token or not isinstance(token, str):
        return None
    now = now or _now()
    h = hashlib.sha256(token.encode()).hexdigest()
    with connect(path) as con:
        r = con.execute("SELECT s.expires_at, u.id, u.email FROM auth_sessions s JOIN users u ON u.id=s.user_id "
                        "WHERE s.token_hash=?", (h,)).fetchone()
        if r is None:
            return None
        if r["expires_at"] < _iso(now):
            con.execute("DELETE FROM auth_sessions WHERE token_hash=?", (h,))
            return None
        return {"id": r["id"], "email": r["email"]}


def logout(token: str | None, path=None) -> None:
    if token:
        with connect(path) as con:
            con.execute("DELETE FROM auth_sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))


def delete_account(user_id: int, path=None) -> None:
    """Deletes the account, its sessions (FK cascade), AI usage counters and all owner-scoped data."""
    owner = owner_key(user_id)
    repository.delete_all(owner, path)
    with connect(path) as con:
        con.execute("DELETE FROM ai_usage WHERE owner=?", (owner,))
        con.execute("DELETE FROM users WHERE id=?", (int(user_id),))


def verify_user_password(user_id: int, password: str, path=None) -> bool:
    """Re-authentication for sensitive actions (e.g. account deletion)."""
    with connect(path) as con:
        r = con.execute("SELECT password_hash FROM users WHERE id=?", (int(user_id),)).fetchone()
    return bool(r) and verify_password(password or "", r["password_hash"])

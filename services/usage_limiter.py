"""Per-user daily AI request quota (cost control). Counts AI requests started, including cache hits."""
from datetime import datetime, timezone

import config
from database.db import connect


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def consume(owner: str, limit: int | None = None, path=None, today: str | None = None) -> bool:
    """Atomically counts one request. False if the daily limit is already reached. limit<=0 disables."""
    limit = config.AI_DAILY_LIMIT if limit is None else limit
    if limit <= 0:
        return True
    with connect(path) as con:
        cur = con.execute("INSERT INTO ai_usage(owner,day,calls) VALUES(?,?,1) "
                          "ON CONFLICT(owner,day) DO UPDATE SET calls=calls+1 WHERE calls<?",
                          (owner, today or _today(), limit))
        return cur.rowcount > 0


def used_today(owner: str, path=None, today: str | None = None) -> int:
    with connect(path) as con:
        r = con.execute("SELECT calls FROM ai_usage WHERE owner=? AND day=?", (owner, today or _today())).fetchone()
        return r[0] if r else 0

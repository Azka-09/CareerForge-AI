import json
from database.db import connect

_COUNTS = {
    "Resumes Analyzed": "SELECT COUNT(DISTINCT resume_name) FROM analyses WHERE session_id=?",
    "Jobs Compared": "SELECT COUNT(*) FROM analyses WHERE session_id=? AND kind='job_match'",
    "Resume Versions Saved": "SELECT COUNT(*) FROM resume_versions WHERE session_id=?",
    "Interview Sessions": "SELECT COUNT(*) FROM interview_sessions WHERE session_id=? AND status='completed'",
}
_SESSION_TABLES = ("analyses", "resume_versions", "interview_sessions", "interview_questions",
                   "roadmaps", "roadmap_tasks", "applications")


def counts(session_id: str, path: str | None = None) -> dict[str, int]:
    """Real counts only; a new session returns zeros."""
    with connect(path) as con:
        return {k: con.execute(q, (session_id,)).fetchone()[0] for k, q in _COUNTS.items()}


def delete_all(session_id: str, path: str | None = None) -> None:
    with connect(path) as con:
        for t in _SESSION_TABLES:
            con.execute(f"DELETE FROM {t} WHERE session_id=?", (session_id,))


def delete_interviews(session_id: str, path=None) -> None:
    with connect(path) as con:
        for t in ("interview_questions", "interview_sessions"):
            con.execute(f"DELETE FROM {t} WHERE session_id=?", (session_id,))


def delete_roadmaps(session_id: str, path=None) -> None:
    with connect(path) as con:
        for t in ("roadmap_tasks", "roadmaps"):
            con.execute(f"DELETE FROM {t} WHERE session_id=?", (session_id,))


# ---- interviews (every query is scoped by session_id) ----
def create_interview(session_id: str, meta: dict, questions: list[dict], path=None) -> int:
    with connect(path) as con:
        cur = con.execute(
            "INSERT INTO interview_sessions(session_id,job_title,company,category,difficulty,num_questions) VALUES(?,?,?,?,?,?)",
            (session_id, meta.get("job_title", ""), meta.get("company", ""), meta.get("category", ""),
             meta.get("difficulty", ""), len(questions)))
        iid = cur.lastrowid
        con.executemany("INSERT INTO interview_questions(session_id,interview_id,idx,category,question) VALUES(?,?,?,?,?)",
                        [(session_id, iid, i, q.get("category", ""), q["question"]) for i, q in enumerate(questions)])
        return iid


def save_answer(session_id: str, interview_id: int, idx: int, answer: str, evaluation: dict | None, path=None) -> None:
    with connect(path) as con:
        con.execute("UPDATE interview_questions SET answer=?, evaluation_json=? WHERE session_id=? AND interview_id=? AND idx=?",
                    (answer, json.dumps(evaluation) if evaluation else None, session_id, interview_id, idx))


def complete_interview(session_id: str, interview_id: int, path=None) -> None:
    with connect(path) as con:
        con.execute("UPDATE interview_sessions SET status='completed' WHERE session_id=? AND id=?", (session_id, interview_id))


def load_interview(session_id: str, interview_id: int, path=None) -> dict | None:
    with connect(path) as con:
        m = con.execute("SELECT * FROM interview_sessions WHERE session_id=? AND id=?", (session_id, interview_id)).fetchone()
        if not m:
            return None
        rows = con.execute("SELECT * FROM interview_questions WHERE session_id=? AND interview_id=? ORDER BY idx",
                           (session_id, interview_id)).fetchall()
    items = [{"category": r["category"], "question": r["question"], "answer": r["answer"] or "",
              "evaluation": json.loads(r["evaluation_json"]) if r["evaluation_json"] else None} for r in rows]
    return {"id": m["id"], "meta": {k: m[k] for k in ("job_title", "company", "category", "difficulty", "status", "created_at")},
            "items": items}


def list_interviews(session_id: str, path=None) -> list[dict]:
    with connect(path) as con:
        return [dict(r) for r in con.execute(
            "SELECT id,job_title,category,difficulty,status,created_at,num_questions FROM interview_sessions "
            "WHERE session_id=? ORDER BY id DESC", (session_id,))]


# ---- roadmaps ----
def save_roadmap(session_id: str, job_title: str, roadmap: dict, path=None) -> int:
    with connect(path) as con:
        return con.execute("INSERT INTO roadmaps(session_id,job_title,roadmap_json) VALUES(?,?,?)",
                           (session_id, job_title, json.dumps(roadmap))).lastrowid


def latest_roadmap(session_id: str, path=None) -> tuple[int, str, dict] | None:
    with connect(path) as con:
        r = con.execute("SELECT id,job_title,roadmap_json FROM roadmaps WHERE session_id=? ORDER BY id DESC LIMIT 1",
                        (session_id,)).fetchone()
    return (r["id"], r["job_title"], json.loads(r["roadmap_json"])) if r else None


def set_task(session_id: str, roadmap_id: int, key: str, done: bool, path=None) -> None:
    with connect(path) as con:
        if not con.execute("SELECT 1 FROM roadmaps WHERE id=? AND session_id=?", (roadmap_id, session_id)).fetchone():
            raise PermissionError("Roadmap does not belong to this session.")
        con.execute("INSERT INTO roadmap_tasks(session_id,roadmap_id,task_key,done) VALUES(?,?,?,?) "
                    "ON CONFLICT(roadmap_id,task_key) DO UPDATE SET done=excluded.done", (session_id, roadmap_id, key, int(done)))


def done_tasks(session_id: str, roadmap_id: int, path=None) -> set[str]:
    with connect(path) as con:
        return {r[0] for r in con.execute("SELECT task_key FROM roadmap_tasks WHERE session_id=? AND roadmap_id=? AND done=1",
                                          (session_id, roadmap_id))}


# ---- privacy controls ----
def delete_interview(session_id: str, interview_id: int, path=None) -> bool:
    """Deletes one interview only if it belongs to session_id. Returns whether something was deleted."""
    with connect(path) as con:
        cur = con.execute("DELETE FROM interview_sessions WHERE id=? AND session_id=?", (interview_id, session_id))
        if cur.rowcount:
            con.execute("DELETE FROM interview_questions WHERE interview_id=? AND session_id=?", (interview_id, session_id))
        return bool(cur.rowcount)


def export_user(session_id: str, path=None) -> dict:
    """All records owned by session_id, JSON-serialisable (no password hashes, no other users' data)."""
    tables = ("analyses", "resume_versions", "interview_sessions", "interview_questions", "roadmaps",
              "roadmap_tasks", "applications")
    with connect(path) as con:
        return {t: [dict(r) for r in con.execute(f"SELECT * FROM {t} WHERE session_id=?", (session_id,))] for t in tables}

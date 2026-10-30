import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import repository as repo
from services import interview_service as isvc, interview_evaluator as ev, career_roadmap_service as rm
from services.llm_service import LLMError

EV = lambda s, miss=(), weak=(): {"score": s, "strengths": [], "weaknesses": list(weak), "missing_points": list(miss),
                                  "recommendations": ["be specific"], "suggested_structure": "", "improved_example": "",
                                  "claims_to_verify": []}
ITEMS = [{"category": "technical", "question": "Explain indexes", "answer": "An index speeds reads", "evaluation": EV(9)},
         {"category": "behavioral", "question": "Describe a conflict", "answer": "We argued", "evaluation": EV(4, ["Result"], ["No STAR"])},
         {"category": "behavioral", "question": "Describe a failure", "answer": "I failed once", "evaluation": EV(6, ["Result"])},
         {"category": "hr", "question": "Why this company?", "answer": "", "evaluation": None}]


def test_normalize_questions():
    raw = [{"question": "Tell me about X?", "category": "hr"}, {"question": "tell me about x?"}, {"question": "hi"},
           {"question": "Explain REST APIs?", "category": "technical"}]
    out = isvc.normalize_questions(raw, "mixed", 5)
    assert [q["category"] for q in out] == ["hr", "technical"]
    assert isvc.normalize_questions(raw, "behavioral", 1)[0]["category"] == "behavioral"
    try: isvc.normalize_questions([{"question": "x"}], "mixed", 3); assert False
    except LLMError: pass


def test_answer_validation():
    assert ev.validate_answer("short") and ev.validate_answer("   ") and ev.validate_answer("A sufficiently long answer.") is None


def test_progress():
    p = ev.progress(ITEMS)
    assert p == {"total": 4, "answered": 3, "evaluated": 3, "pct": 75.0}
    assert ev.progress([])["pct"] == 0.0


def test_report():
    r = ev.build_report(ITEMS)
    assert r["overall"] == round((9 + 4 + 6) / 3, 1) and r["by_category"] == {"technical": 9.0, "behavioral": 5.0}
    assert r["strong"] == [0] and r["needs_work"] == [1] and r["unanswered"] == [3] and r["topics"][0] == "Result"
    assert ev.build_report([])["overall"] is None


def test_report_markdown_and_pdf():
    md = ev.report_markdown(ev.build_report(ITEMS), ITEMS, {"job_title": "Eng", "category": "mixed", "difficulty": "beginner"})
    assert "Overall score" in md and "Q2" in md and "advisory" in md
    pdf = ev.report_pdf(md + "\nSpecial <chars> & more")
    assert pdf.startswith(b"%PDF") and len(pdf) > 500


def test_interview_persistence_and_isolation(tmp_path):
    db = str(tmp_path / "t.db")
    iid = repo.create_interview("A", {"job_title": "Eng", "category": "mixed", "difficulty": "beginner"},
                                [{"question": "Q one?", "category": "hr"}, {"question": "Q two?", "category": "technical"}], db)
    repo.save_answer("A", iid, 0, "my answer", EV(7), db)
    got = repo.load_interview("A", iid, db)
    assert got["items"][0]["answer"] == "my answer" and got["items"][0]["evaluation"]["score"] == 7 and got["items"][1]["answer"] == ""
    assert repo.load_interview("B", iid, db) is None and repo.list_interviews("B", db) == []
    assert repo.counts("A", db)["Interview Sessions"] == 0
    repo.complete_interview("A", iid, db)
    assert repo.counts("A", db)["Interview Sessions"] == 1
    repo.delete_interviews("A", db)
    assert repo.list_interviews("A", db) == []


def test_old_phase1_database_is_migrated(tmp_path):
    import sqlite3
    db = str(tmp_path / "old.db"); c = sqlite3.connect(db)
    c.execute("CREATE TABLE interview_sessions(id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, job_title TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("INSERT INTO interview_sessions(session_id, job_title) VALUES('A','Old')"); c.commit(); c.close()
    assert repo.list_interviews("A", db)[0]["job_title"] == "Old"          # old row survives
    iid = repo.create_interview("A", {"job_title": "New"}, [{"question": "Q?"}], db)
    assert repo.load_interview("A", iid, db)["meta"]["job_title"] == "New"


ROAD = {"skills": [{"skill": "Spark", "horizon": "short", "topics": ["RDDs", "SQL"], "exercise": "word count", "project": "ETL"},
                   {"skill": "Airflow", "horizon": "advanced", "topics": [], "exercise": "", "project": ""}],
        "practical_projects": ["Pipeline"], "portfolio_improvements": ["README"], "interview_prep": ["Mock"]}


def test_task_list_and_progress():
    t = rm.task_list(ROAD)
    keys = [x["key"] for x in t]
    assert keys == ["skill0:topic0", "skill0:topic1", "skill0:exercise", "skill0:project", "project0", "portfolio0", "interview0"]
    p = rm.progress(t, {"skill0:topic0", "project0", "stale-key"})
    assert p["done"] == 2 and p["total"] == 7 and p["pct"] == round(200 / 7, 1)
    assert p["by_group"]["Short-term goals"] == {"done": 1, "total": 4}
    assert rm.progress([], set())["pct"] == 0.0


def test_roadmap_persistence_and_isolation(tmp_path):
    db = str(tmp_path / "r.db")
    rid = repo.save_roadmap("A", "Data Eng", ROAD, db)
    repo.set_task("A", rid, "project0", True, db); repo.set_task("A", rid, "skill0:topic0", True, db)
    repo.set_task("A", rid, "project0", False, db)
    assert repo.done_tasks("A", rid, db) == {"skill0:topic0"}
    assert repo.latest_roadmap("A", db)[2] == ROAD and repo.latest_roadmap("B", db) is None
    try: repo.set_task("B", rid, "x", True, db); assert False
    except PermissionError: pass
    repo.delete_roadmaps("A", db)
    assert repo.latest_roadmap("A", db) is None and repo.done_tasks("A", rid, db) == set()


def test_gap_rows_use_deterministic_comparison():
    rows = rm.build_gap_rows(None, "I use Python daily", {"required_skills": ["Python", "Rust"]})
    assert {r["skill"]: r["status"] for r in rows} == {"Python": "mentioned", "Rust": "not_found"}


def test_delete_all_covers_new_tables(tmp_path):
    db = str(tmp_path / "d.db")
    iid = repo.create_interview("A", {}, [{"question": "Q?"}], db); rid = repo.save_roadmap("A", "x", ROAD, db)
    repo.set_task("A", rid, "project0", True, db); repo.delete_all("A", db)
    assert repo.load_interview("A", iid, db) is None and repo.latest_roadmap("A", db) is None

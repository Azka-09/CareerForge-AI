from services.llm_service import structured, doc
from services import job_matcher as jm

GROUPS = {"short": "Short-term goals", "medium": "Medium-term goals", "advanced": "Advanced goals"}
SYSTEM = ("Create a personalised career roadmap from the resume, target job and the skill-evidence table. "
          "Use the evidence statuses: do not treat 'not_found' as proof the person lacks a skill, ask them to verify. "
          "For each skill give why it matters, topics to learn, a practical exercise, a suggested project and an "
          "estimated_duration (always an estimate). Never advise adding a skill to the resume unless the person can "
          "genuinely demonstrate it. Also give practical_projects, portfolio_improvements and interview_prep. "
          "Existing strengths go in strengths. Horizon is short, medium or advanced.")


def build_gap_rows(resume: dict | None, resume_text: str, req: dict, embed=None) -> list[dict]:
    sec = jm.sections_from(resume, resume_text)
    return jm.compare_skills(req.get("required_skills", []) + req.get("preferred_skills", []), sec, embed)


def generate(resume_json: str, job_text: str, title: str, goals: str, gap_rows: list[dict], cache=None):
    from models.roadmap_models import Roadmap
    evidence = "\n".join(f"- {r['skill']}: {r['status']}" for r in gap_rows) or "(no skill list available)"
    user = (doc("resume", resume_json) + "\n" + doc("job_description", job_text) +
            f"\nTarget position: {title}\nCareer goals: {goals or 'not stated'}\nSkill evidence:\n{evidence}")
    return structured(SYSTEM, user, Roadmap, cache)


def task_list(roadmap: dict) -> list[dict]:
    """Stable task keys so saved checkbox state survives reloads."""
    t = []
    for i, s in enumerate(roadmap.get("skills", [])):
        g = GROUPS.get(s.get("horizon", "medium"), GROUPS["medium"])
        t += [{"key": f"skill{i}:topic{j}", "group": g, "label": f"{s['skill']}: learn {x}"} for j, x in enumerate(s.get("topics", []))]
        if s.get("exercise"): t.append({"key": f"skill{i}:exercise", "group": g, "label": f"{s['skill']}: {s['exercise']}"})
        if s.get("project"): t.append({"key": f"skill{i}:project", "group": g, "label": f"{s['skill']} project: {s['project']}"})
    for key, group, field in (("project", "Practical projects", "practical_projects"),
                              ("portfolio", "Portfolio improvements", "portfolio_improvements"),
                              ("interview", "Interview preparation", "interview_prep")):
        t += [{"key": f"{key}{i}", "group": group, "label": x} for i, x in enumerate(roadmap.get(field, []))]
    return t


def progress(tasks: list[dict], done: set[str]) -> dict:
    valid = {t["key"] for t in tasks}
    by_group: dict[str, list[int]] = {}
    for t in tasks:
        d = by_group.setdefault(t["group"], [0, 0]); d[1] += 1; d[0] += t["key"] in done
    n = sum(1 for k in done if k in valid)
    return {"total": len(tasks), "done": n, "pct": round(100 * n / len(tasks), 1) if tasks else 0.0,
            "by_group": {g: {"done": a, "total": b} for g, (a, b) in by_group.items()}}

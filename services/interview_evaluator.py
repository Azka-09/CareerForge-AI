import io
from collections import Counter
from xml.sax.saxutils import escape

from services.llm_service import structured, doc

MIN_ANSWER_CHARS = 15
SYSTEM = ("Evaluate the interview answer on relevance, technical correctness (if applicable), clarity, completeness, "
          "logical structure, supporting examples, and alignment with the candidate's ACTUAL experience in the resume. "
          "Score 0-10. Do NOT reward claims of experience or skills that the resume does not support: list such claims "
          "in claims_to_verify and lower the score. {star}Give strengths, weaknesses, missing_points, recommendations, "
          "suggested_structure, and an improved_example that uses only facts from the resume and the candidate's answer "
          "(use placeholders like [your result] where detail is missing). Feedback is advisory.")
STAR = "This is a behavioral question: assess use of STAR (Situation, Task, Action, Result) and say which parts are missing. "


def validate_answer(answer: str) -> str | None:
    """Returns an error message, or None if OK."""
    if len((answer or "").strip()) < MIN_ANSWER_CHARS:
        return "Please write a fuller answer before requesting feedback."
    return None


def evaluate(question: dict, answer: str, resume_json: str, job_text: str = "", cache=None) -> dict:
    from models.interview_models import Evaluation
    err = validate_answer(answer)
    if err:
        raise ValueError(err)
    system = SYSTEM.format(star=STAR if question.get("category") == "behavioral" else "")
    user = (doc("resume", resume_json) + (("\n" + doc("job_description", job_text)) if job_text.strip() else "")
            + f"\nQuestion: {question['question']}\n" + doc("answer", answer))
    return structured(system, user, Evaluation, cache).model_dump()


def progress(items: list[dict]) -> dict:
    ans = sum(1 for i in items if i.get("answer", "").strip())
    ev = sum(1 for i in items if i.get("evaluation"))
    return {"total": len(items), "answered": ans, "evaluated": ev,
            "pct": round(100 * ans / len(items), 1) if items else 0.0}


def build_report(items: list[dict]) -> dict:
    scored = [(n, i) for n, i in enumerate(items) if i.get("evaluation")]
    scores = [i["evaluation"]["score"] for _, i in scored]
    by_cat: dict[str, list[int]] = {}
    for _, i in scored:
        by_cat.setdefault(i["category"], []).append(i["evaluation"]["score"])
    topics = Counter(t.strip() for _, i in scored for t in i["evaluation"]["missing_points"] + i["evaluation"]["weaknesses"] if t.strip())
    return {
        "evaluated": len(scored), "total": len(items),
        "overall": round(sum(scores) / len(scores), 1) if scores else None,
        "by_category": {c: round(sum(v) / len(v), 1) for c, v in by_cat.items()},
        "strong": [n for n, i in scored if i["evaluation"]["score"] >= 8],
        "needs_work": [n for n, i in scored if i["evaluation"]["score"] <= 5],
        "unanswered": [n for n, i in enumerate(items) if not i.get("answer", "").strip()],
        "topics": [t for t, _ in topics.most_common(8)],
    }


def report_markdown(report: dict, items: list[dict], meta: dict) -> str:
    L = [f"# Interview Performance Report", f"*{meta.get('job_title', '')} · {meta.get('category', '')} · {meta.get('difficulty', '')}*", "",
         "AI feedback is advisory and may be incorrect.", ""]
    if report["overall"] is None:
        L.append("No answers were evaluated yet.")
    else:
        L += [f"**Overall score:** {report['overall']}/10 ({report['evaluated']} of {report['total']} questions evaluated)", "", "## Scores by category"]
        L += [f"- {c.title()}: {s}/10" for c, s in report["by_category"].items()]
    for title, idxs in (("Strong answers", report["strong"]), ("Answers needing improvement", report["needs_work"])):
        L += ["", f"## {title}"] + ([f"- Q{n+1} ({items[n]['evaluation']['score']}/10): {items[n]['question']}" for n in idxs] or ["- None"])
    L += ["", "## Recommended topics for further preparation"] + ([f"- {t}" for t in report["topics"]] or ["- None identified"])
    L += ["", "## Question details"]
    for n, i in enumerate(items):
        ev = i.get("evaluation")
        L += ["", f"### Q{n+1}. {i['question']}", f"**Your answer:** {i.get('answer') or '(not answered)'}"]
        if ev:
            L += [f"**Score:** {ev['score']}/10"] + [f"- Improve: {r}" for r in ev["recommendations"]]
            L += [f"- Verify before claiming: {c}" for c in ev["claims_to_verify"]]
    return "\n".join(L)


def report_pdf(markdown: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    st = getSampleStyleSheet(); buf = io.BytesIO()
    story = []
    for line in markdown.splitlines():
        if not line.strip():
            story.append(Spacer(1, 6)); continue
        style = st["Heading1"] if line.startswith("# ") else st["Heading2"] if line.startswith("## ") else st["Heading3"] if line.startswith("### ") else st["BodyText"]
        text = escape(line.lstrip("#- ").strip()).replace("**", "")
        story.append(Paragraph(("• " if line.startswith("- ") else "") + text, style))
    SimpleDocTemplate(buf, pagesize=A4).build(story)
    data = buf.getvalue()
    if not data.startswith(b"%PDF"):
        raise RuntimeError("PDF generation failed")
    return data

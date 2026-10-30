from services.llm_service import structured, doc, LLMError

CATEGORIES = ["technical", "behavioral", "project", "hr", "mixed"]
DIFFICULTY = ["beginner", "intermediate", "advanced"]
MAX_Q = 15
SYSTEM = ("Generate interview questions personalised to the candidate's resume and the job. "
          "Questions may probe gaps but must not assume the candidate has skills the resume lacks. "
          "Return {{\"questions\": [{{question, category, focus}}]}} with category one of technical, behavioral, project, hr. "
          "Category requested: {category}. Difficulty: {difficulty}. Exactly {n} distinct questions. "
          "Target role: {title}{company}.")


def normalize_questions(items: list[dict], category: str, n: int) -> list[dict]:
    """Validate/clean model output: drop blanks and duplicates, enforce category and count."""
    seen, out = set(), []
    for q in items:
        text = (q.get("question") or "").strip()
        if len(text) < 8 or text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append({"question": text, "category": category if category != "mixed" else q.get("category", "technical"),
                    "focus": q.get("focus", "")})
    if not out:
        raise LLMError("The AI did not return usable questions. Please try again.")
    return out[:n]


def generate_questions(resume_json: str, job_text: str, title: str, company: str, category: str,
                       difficulty: str, n: int, cache=None) -> list[dict]:
    from models.interview_models import QuestionSet
    if category not in CATEGORIES or difficulty not in DIFFICULTY:
        raise ValueError("Unknown category or difficulty.")
    n = max(1, min(int(n), MAX_Q))
    system = SYSTEM.format(category=category, difficulty=difficulty, n=n, title=title or "not specified",
                           company=f" at {company}" if company else "")
    user = doc("resume", resume_json) + (("\n" + doc("job_description", job_text)) if job_text.strip() else "")
    qs = structured(system, user, QuestionSet, cache)
    return normalize_questions([q.model_dump() for q in qs.questions], category, n)

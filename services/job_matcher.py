"""Transparent job matching: lexical + semantic (TF-IDF by default, Sentence Transformers optional)."""
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from utils.scoring import weighted_score

ALIASES = {"js": "javascript", "ts": "typescript", "k8s": "kubernetes", "ml": "machine learning",
           "nlp": "natural language processing", "postgres": "postgresql", "gcp": "google cloud",
           "ci/cd": "continuous integration", "sklearn": "scikit-learn"}
STATUS_WEIGHT = {"demonstrated": 1.0, "mentioned": 0.6, "needs_verification": 0.4, "not_found": 0.0}
SEMANTIC_VERIFY = 0.55      # similarity above which a skill is flagged "needs verification"
SIM_SCALE = 0.35            # cosine at/above which text-alignment counts as full
DEGREE_RANK = {"associate": 1, "bachelor": 2, "master": 3, "phd": 4, "doctor": 4}


def variants(skill: str) -> set[str]:
    s = skill.lower().strip()
    out = {s}
    for a, full in ALIASES.items():
        if s == a: out.add(full)
        if s == full: out.add(a)
    return out


def contains(term: str, text: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(term)}(?![\w])", text.lower()) is not None


def sections_from(resume: dict | None, full_text: str) -> dict:
    """Build searchable section text from ResumeData.model_dump() (or full text only)."""
    if not resume:
        return {"experience": "", "projects": "", "skills": "", "education": "", "full": full_text, "structured": False}
    exp = "\n".join(f"{e['title']} {e['company']}\n" + "\n".join(e["bullets"]) for e in resume["experience"])
    proj = "\n".join(f"{p['name']}\n{p['description']}\n{' '.join(p['technologies'])}" for p in resume["projects"])
    edu = "\n".join(f"{e['degree']} {e['institution']}" for e in resume["education"])
    return {"experience": exp, "projects": proj, "skills": ", ".join(resume["skills"]), "education": edu,
            "full": full_text, "structured": True}


def keyword_coverage(keywords: list[str], text: str) -> tuple[list[str], list[str], float]:
    hit = [k for k in keywords if any(contains(v, text) for v in variants(k))]
    miss = [k for k in keywords if k not in hit]
    return hit, miss, (len(hit) / len(keywords) if keywords else 0.0)


def extract_keywords_basic(job_description: str, n: int = 25) -> list[str]:
    """Deterministic fallback (no LLM): most frequent non-stopword terms."""
    if not job_description.strip():
        return []
    cv = CountVectorizer(ngram_range=(1, 2), stop_words="english", token_pattern=r"(?u)\b[a-zA-Z][\w+#.]+\b")
    try:
        m = cv.fit_transform([job_description])
    except ValueError:
        return []
    counts = np.asarray(m.sum(axis=0)).ravel()
    terms = cv.get_feature_names_out()
    return [terms[i] for i in np.argsort(-counts)[:n]]


def _lines(text: str) -> list[str]:
    return [l.strip() for l in re.split(r"[\n.]", text) if len(l.strip()) > 3]


def semantic_best(skills: list[str], lines: list[str], embed=None) -> list[tuple[float, str]]:
    """Best similar resume line per skill. `embed(list[str]) -> ndarray` enables Sentence Transformers."""
    if not skills or not lines:
        return [(0.0, "")] * len(skills)
    if embed:
        sim = cosine_similarity(embed(skills), embed(lines))
    else:
        v = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit(skills + lines)
        sim = cosine_similarity(v.transform(skills), v.transform(lines))
    return [(float(sim[i].max()), lines[int(sim[i].argmax())]) for i in range(len(skills))]


def compare_skills(skills: list[str], sec: dict, embed=None) -> list[dict]:
    """Statuses: demonstrated | mentioned | needs_verification | not_found.
    'not_found' means no lexical or semantic evidence in the text - NOT proof the user lacks the skill."""
    work = sec["experience"] + "\n" + sec["projects"]
    rows, pending = [], []
    for s in skills:
        vs = variants(s)
        if sec["structured"] and any(contains(v, work) for v in vs):
            ev = next((l for l in _lines(work) if any(contains(v, l) for v in vs)), "")
            rows.append({"skill": s, "status": "demonstrated", "evidence": ev})
        elif any(contains(v, sec["full"]) for v in vs):
            ev = next((l for l in _lines(sec["full"]) if any(contains(v, l) for v in vs)), "")
            rows.append({"skill": s, "status": "mentioned", "evidence": ev})
        else:
            rows.append({"skill": s, "status": "not_found", "evidence": ""}); pending.append(len(rows) - 1)
    if pending:
        best = semantic_best([rows[i]["skill"] for i in pending], _lines(sec["full"]), embed)
        for i, (score, line) in zip(pending, best):
            if score >= SEMANTIC_VERIFY:
                rows[i].update(status="needs_verification", evidence=line)
    return rows


def _align(a: str, b: str) -> float:
    if not a.strip() or not b.strip():
        return 0.0
    try:
        m = TfidfVectorizer(stop_words="english").fit_transform([a, b])
    except ValueError:
        return 0.0
    return float(min(1.0, cosine_similarity(m[0], m[1])[0, 0] / SIM_SCALE))


def _education_score(req: list[str], edu_text: str) -> float:
    if not req:
        return 1.0
    need = max((r for t in req for w, r in DEGREE_RANK.items() if w in t.lower()), default=0)
    if need == 0:
        return 1.0
    have = max((r for w, r in DEGREE_RANK.items() if w in edu_text.lower() or
                (w == "bachelor" and re.search(r"\b(b\.?s\.?c?|b\.?a|b\.?tech|be)\b", edu_text.lower()))), default=0)
    return 1.0 if have >= need else 0.0


def match(resume: dict | None, full_text: str, req: dict, job_text: str = "", weights=None, embed=None) -> dict:
    sec = sections_from(resume, full_text)
    req_rows = compare_skills(req.get("required_skills", []), sec, embed)
    pref_rows = compare_skills(req.get("preferred_skills", []), sec, embed)
    kw = req.get("keywords") or extract_keywords_basic(job_text)
    kw_hit, kw_miss, kw_ratio = keyword_coverage(kw, full_text)
    jd = job_text or " ".join(req.get("experience_requirements", []) + req.get("required_skills", []))
    projects = []
    for p in (resume or {}).get("projects", []):
        projects.append({"name": p["name"], "relevance": round(_align(jd, f"{p['name']} {p['description']} {' '.join(p['technologies'])}"), 2)})
    projects.sort(key=lambda p: -p["relevance"])
    exp_req = " ".join(req.get("experience_requirements", [])) or jd
    comps = {
        "required_skills": (sum(STATUS_WEIGHT[r["status"]] for r in req_rows) / len(req_rows)) if req_rows else 0.0,
        "experience": _align(exp_req, sec["experience"] or full_text),
        "projects": projects[0]["relevance"] if projects else 0.0,
        "education": _education_score(req.get("education_requirements", []), sec["education"] or full_text),
        "keywords": kw_ratio,
    }
    return {"score": weighted_score(comps, weights), "components": comps, "required": req_rows,
            "preferred": pref_rows, "projects": projects, "keywords_found": kw_hit, "keywords_missing": kw_miss,
            "keywords_source": "job description analysis" if req.get("keywords") else "basic frequency extraction"}

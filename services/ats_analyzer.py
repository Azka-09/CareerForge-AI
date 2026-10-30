"""Heuristic ATS-style checks. Every result is an ESTIMATE, not an official ATS score."""
import re
from services.job_matcher import keyword_coverage, extract_keywords_basic
from utils.scoring import weighted_score

ATS_WEIGHTS = {"contact": .15, "headings": .20, "structure": .15, "extraction": .15, "formatting": .10, "keywords": .25}
HEADINGS = {"experience": r"(?:work\s+|professional\s+)?experience|employment(?:\s+history)?",
            "education": r"education", "skills": r"(?:technical\s+)?skills",
            "projects": r"projects?", "summary": r"(?:professional\s+)?summary|profile|objective",
            "certifications": r"certifications?"}
REQUIRED = ("experience", "education", "skills")


def _cat(name, score, explanation, issues, source="detected"):
    return {"name": name, "score": round(max(0.0, min(1.0, score)), 2), "explanation": explanation,
            "issues": issues, "source": source}


def analyze(text: str, keywords: list[str] | None = None, job_text: str = "", weights=None) -> dict:
    cats, low = [], text.lower()
    # Contact
    has = {"email": bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)),
           "phone": bool(re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", text)),
           "link": bool(re.search(r"linkedin\.com|github\.com|https?://", low))}
    issues = [f"No {k} detected in the extracted text." for k, v in has.items() if not v and k != "link"]
    cats.append(_cat("Contact information", (has["email"] * .5 + has["phone"] * .4 + has["link"] * .1),
                     "Checks for an email, phone number and profile link in the extracted text.", issues))
    # Headings
    found = {k for k, p in HEADINGS.items() if re.search(rf"^\s*(?:{p})\s*:?\s*$", text, re.I | re.M)}
    miss = [k for k in REQUIRED if k not in found]
    cats.append(_cat("Section headings", 1 - len(miss) / len(REQUIRED) + (0 if miss else 0),
                     "Looks for standard headings (Experience, Education, Skills) on their own line.",
                     [f"Standard '{m.title()}' heading not detected." for m in miss]))
    # Structure
    words, lines = len(text.split()), [l for l in text.splitlines() if l.strip()]
    bullets = sum(1 for l in lines if re.match(r"\s*[-•*▪●]", l))
    s_issues, s = [], 1.0
    if words < 150: s -= .4; s_issues.append(f"Very short ({words} words).")
    if words > 1200: s -= .3; s_issues.append(f"Long ({words} words); consider trimming.")
    if bullets < 3: s -= .3; s_issues.append("Few bullet points detected.")
    cats.append(_cat("Resume structure", s, "Checks length and use of bullet points.", s_issues))
    # Extraction quality
    alpha = sum(c.isalpha() for c in text) / max(1, len(text))
    odd = len(re.findall(r"[\ufffd\u25a1]", text))
    e_issues = []
    if alpha < .6: e_issues.append("Unusually low share of letters; text may be garbled.")
    if odd: e_issues.append(f"{odd} unreadable characters found.")
    cats.append(_cat("Text extraction quality", 1.0 - (.4 if alpha < .6 else 0) - (.3 if odd else 0),
                     "Checks whether the text extracted cleanly.", e_issues))
    # Formatting (only what is detectable from text)
    f_issues = []
    if text.count(" | ") > 3: f_issues.append("Table-like content detected; some ATS parsers read tables poorly.")
    if len(re.findall(r" {4,}|\t", text)) > 10: f_issues.append("Heavy spacing/tab layout suggests multiple columns.")
    cats.append(_cat("Formatting concerns", 1 - .35 * len(f_issues),
                     "Only formatting visible in extracted text can be detected (not fonts, images or headers/footers).",
                     f_issues))
    # Keywords
    kw_note = None
    if job_text.strip() or keywords:
        kws = keywords or extract_keywords_basic(job_text)
        hit, missing, ratio = keyword_coverage(kws, text)
        src = "AI-extracted job keywords" if keywords else "basic frequency extraction (no AI)"
        cats.append(_cat("Keyword alignment", ratio, f"Share of job keywords found in the resume ({src}).",
                         [f"Not found in text: {', '.join(missing[:10])}"] if missing else [], "estimated"))
    comps = {c["name"]: c["score"] for c in cats}
    keymap = dict(zip([c["name"] for c in cats], ["contact", "headings", "structure", "extraction", "formatting", "keywords"]))
    score = weighted_score({keymap[k]: v for k, v in comps.items()}, weights or ATS_WEIGHTS)
    return {"score": score, "categories": cats, "headings_found": sorted(found),
            "disclaimer": "Estimated compatibility from transparent heuristics. Not an official ATS score; "
                          "real systems differ."}

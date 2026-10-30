import re
from models.resume_models import ResumeData, Rewrite
from services.llm_service import structured, doc

PROMPTS = {
    "improve": "Rewrite the text to be clearer, more professional and achievement-oriented.",
    "grammar": "Only correct grammar, spelling and punctuation. Do not change meaning or wording otherwise.",
}
RULES = ("Use ONLY facts present in the original or context. Do NOT add numbers, metrics, tools, employers or "
         "achievements that are not there. If a stronger version needs missing details (e.g. impact, scale), "
         "put short questions for the user in needs_info instead of guessing. Put the rewritten text in 'improved'.")
SKILLS = ("Organise these skills into labelled groups, one per line as 'Group: skill, skill'. "
          "Use only the listed skills; do not add new ones.")


def suggest(kind: str, original: str, mode: str = "improve", context: str = "", nonce: int = 0, cache=None) -> Rewrite:
    """kind: summary|experience|project|skills. `nonce` bumps to force a regenerate past the cache."""
    system = SKILLS if kind == "skills" else f"{PROMPTS[mode]} {RULES} Section type: {kind}."
    user = doc("original", original) + (("\n" + doc("context", context)) if context else "") + f"\n(variant {nonce})"
    return structured(system, user, Rewrite, cache)


def invented_numbers(original: str, improved: str) -> list[str]:
    """Deterministic guard: numbers appearing in the rewrite but not the original."""
    nums = lambda s: set(re.findall(r"\d[\d,.]*%?", s))
    return sorted(nums(improved) - nums(original))


def invented_skills(original: list[str], improved_text: str) -> list[str]:
    have = {s.lower() for s in original}
    items = [re.sub(r"^[^:]+:", "", ln).split(",") for ln in improved_text.splitlines()]
    flat = [i.strip() for grp in items for i in grp if i.strip()]
    return [s for s in flat if s.lower() not in have]


def apply_suggestion(data: ResumeData, key: str, text: str) -> ResumeData:
    """key: summary | skills | exp:<i> | proj:<i>. Returns an updated copy; original is never mutated."""
    d = data.model_copy(deep=True)
    if key == "summary":
        d.summary = text.strip()
    elif key == "skills":
        parts = [re.sub(r"^[^:]+:", "", ln) for ln in text.splitlines()]
        d.skills = [s.strip() for p in parts for s in p.split(",") if s.strip()]
    elif key.startswith("exp:"):
        d.experience[int(key[4:])].bullets = [b.lstrip("-• ").strip() for b in text.splitlines() if b.strip()]
    elif key.startswith("proj:"):
        d.projects[int(key[5:])].description = text.strip()
    else:
        raise ValueError(f"Unknown section key: {key}")
    return d

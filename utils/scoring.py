"""Transparent weighted scoring. Weights are configurable and normalised."""
DEFAULT_WEIGHTS = {"required_skills": 0.40, "experience": 0.25, "projects": 0.15,
                   "education": 0.10, "keywords": 0.10}


def weighted_score(components: dict[str, float], weights: dict[str, float] | None = None) -> float:
    """components: 0..1 per key. Returns a 0..100 estimate (not an official ATS score)."""
    w = weights or DEFAULT_WEIGHTS
    total = sum(w.get(k, 0) for k in components)
    if total <= 0:
        return 0.0
    s = sum(max(0.0, min(1.0, v)) * w.get(k, 0) for k, v in components.items())
    return round(100 * s / total, 1)

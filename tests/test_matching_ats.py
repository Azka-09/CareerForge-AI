import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from services import job_matcher as jm
from services import ats_analyzer as ats

RESUME = """Jane Doe
jane@example.com +1 415 555 0100 github.com/jane
Summary
Backend engineer.
Experience
- Built REST APIs in Python and deployed on Kubernetes
- Led migration of services to PostgreSQL
- Wrote CI pipelines
Skills
Python, SQL, Docker, Git
Education
BSc Computer Science
"""
DATA = {"experience": [{"title": "Engineer", "company": "Acme", "dates": "", "bullets": [
            "Built REST APIs in Python and deployed on k8s", "Migrated services to Postgres"]}],
        "projects": [{"name": "Chat bot", "description": "NLP chatbot", "technologies": ["Python"]}],
        "skills": ["Python", "SQL", "Docker"], "education": [{"degree": "BSc Computer Science", "institution": "", "dates": ""}]}


def test_alias_and_status():
    sec = jm.sections_from(DATA, RESUME)
    r = {x["skill"]: x["status"] for x in jm.compare_skills(["Kubernetes", "PostgreSQL", "SQL", "Rust"], sec)}
    assert r["Kubernetes"] == "demonstrated"      # alias k8s
    assert r["PostgreSQL"] == "demonstrated"       # alias postgres
    assert r["SQL"] == "mentioned"                 # only in skills list
    assert r["Rust"] == "not_found"


def test_text_only_never_demonstrated():
    sec = jm.sections_from(None, RESUME)
    r = jm.compare_skills(["Python"], sec)
    assert r[0]["status"] == "mentioned"


def test_match_score_range_and_components():
    req = {"required_skills": ["Python", "Kubernetes", "Rust"], "keywords": ["REST", "Python"], "education_requirements": ["Bachelor's degree"]}
    out = jm.match(DATA, RESUME, req, job_text="Python backend REST Kubernetes engineer")
    assert 0 <= out["score"] <= 100
    assert out["components"]["education"] == 1.0
    assert out["projects"][0]["name"] == "Chat bot"
    assert out["components"]["required_skills"] == (1 + 1 + 0) / 3


def test_education_missing_degree():
    assert jm._education_score(["Master's degree"], "BSc Computer Science") == 0.0


def test_keyword_coverage_special_chars():
    hit, miss, r = jm.keyword_coverage(["C++", "Go"], "I know C++ and golang")
    assert hit == ["C++"] and miss == ["Go"] and r == 0.5


def test_ats_good_resume():
    out = ats.analyze(RESUME, job_text="Python Kubernetes REST engineer")
    assert 0 <= out["score"] <= 100 and "Not an official ATS score" in out["disclaimer"]
    names = {c["name"] for c in out["categories"]}
    assert "Keyword alignment" in names


def test_ats_flags_problems_and_no_keywords_without_job():
    out = ats.analyze("hello world")
    cats = {c["name"]: c for c in out["categories"]}
    assert "Keyword alignment" not in cats
    assert cats["Contact information"]["issues"] and cats["Section headings"]["issues"]
    assert out["score"] < 50


def test_empty_job_keywords():
    assert jm.extract_keywords_basic("   ") == []

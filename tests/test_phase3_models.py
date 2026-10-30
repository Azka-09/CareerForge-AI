"""Needs pydantic + pytest. Mocks the LLM transport."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from pydantic import ValidationError
from models.interview_models import Evaluation
from models.roadmap_models import Roadmap
from models.rag_models import RAGAnswer
from services import llm_service, interview_service as isvc, interview_evaluator as ev, career_roadmap_service as rm


def mock(monkeypatch, reply):
    monkeypatch.setattr(llm_service, "_complete", lambda s, u: reply)


def test_score_bounds():
    for bad in (-1, 11):
        with pytest.raises(ValidationError):
            Evaluation(score=bad)
    assert Evaluation(score=10).score == 10


def test_bad_horizon_rejected():
    with pytest.raises(ValidationError):
        Roadmap.model_validate({"skills": [{"skill": "x", "horizon": "someday"}]})


def test_generate_questions_validates_and_trims(monkeypatch):
    qs = [{"question": f"Question number {i}?", "category": "technical"} for i in range(6)]
    mock(monkeypatch, json.dumps({"questions": qs}))
    assert len(isvc.generate_questions("{}", "", "Eng", "", "technical", "beginner", 3)) == 3


def test_generate_questions_rejects_bad_options():
    with pytest.raises(ValueError):
        isvc.generate_questions("{}", "", "Eng", "", "nonsense", "beginner", 3)


def test_evaluate_blocks_short_answer_without_calling_llm(monkeypatch):
    monkeypatch.setattr(llm_service, "_complete", lambda s, u: pytest.fail("LLM called"))
    with pytest.raises(ValueError):
        ev.evaluate({"question": "Q?", "category": "hr"}, "no", "{}")


def test_evaluate_returns_dict_and_rejects_invalid_score(monkeypatch):
    mock(monkeypatch, json.dumps({"score": 7, "strengths": ["clear"]}))
    assert ev.evaluate({"question": "Q?", "category": "behavioral"}, "A long enough answer here.", "{}")["score"] == 7
    mock(monkeypatch, json.dumps({"score": 42}))
    with pytest.raises(llm_service.LLMError):
        ev.evaluate({"question": "Q?", "category": "hr"}, "A long enough answer here.", "{}")


def test_roadmap_generation(monkeypatch):
    mock(monkeypatch, json.dumps({"skills": [{"skill": "Spark", "horizon": "short", "topics": ["RDD"], "estimated_duration": "~3 weeks"}]}))
    r = rm.generate("{}", "job", "Eng", "", [{"skill": "Spark", "status": "not_found"}])
    assert r.skills[0].skill == "Spark"


def test_rag_answer_defaults():
    assert RAGAnswer(answer="x").sufficient is True

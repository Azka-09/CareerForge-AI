"""Needs pydantic. Mocks the LLM transport; no network."""
import sys, os, json
import types
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from pydantic import ValidationError
from models.resume_models import ResumeData, Rewrite, AnalysisReport
from services import llm_service, resume_enhancer as enh, resume_analyzer as ana


def mock(monkeypatch, replies):
    calls = []
    def fake(system, user):
        calls.append(user); r = replies.pop(0)
        if isinstance(r, Exception): raise r
        return r
    monkeypatch.setattr(llm_service, "_complete", fake)
    return calls


def test_models_default_empty():
    d = ResumeData()
    assert d.summary == "" and d.experience == [] and d.personal.email == ""


def test_invalid_priority_rejected():
    with pytest.raises(ValidationError):
        AnalysisReport.model_validate({"findings": [{"area": "a", "kind": "strength", "text": "t", "priority": "urgent"}]})


def test_retry_on_invalid_json(monkeypatch):
    calls = mock(monkeypatch, ["not json", json.dumps({"improved": "ok"})])
    assert llm_service.structured("s", "u", Rewrite).improved == "ok" and len(calls) == 2


def test_gives_up_with_clear_error(monkeypatch):
    mock(monkeypatch, ["x", "y"])
    with pytest.raises(llm_service.LLMError):
        llm_service.structured("s", "u", Rewrite)


def test_cache_avoids_duplicate_calls(monkeypatch):
    calls = mock(monkeypatch, [json.dumps({"improved": "a"})]); cache = {}
    llm_service.structured("s", "u", Rewrite, cache); llm_service.structured("s", "u", Rewrite, cache)
    assert len(calls) == 1


def test_missing_key_raises_unavailable(monkeypatch):
    monkeypatch.setattr(llm_service.config, "LLM_API_KEY", "")
    with pytest.raises(llm_service.LLMUnavailable):
        llm_service._complete("s", "u")


def test_session_api_key_overrides_server_key_and_is_restored(monkeypatch):
    monkeypatch.setattr(llm_service.config, "LLM_API_KEY", "server-key")
    assert llm_service.active_api_key() == "server-key"
    with llm_service.api_key_context("  user-key  "):
        assert llm_service.active_api_key() == "user-key"
        assert llm_service.has_api_key()
    assert llm_service.active_api_key() == "server-key"


def test_client_uses_current_session_key_without_sharing(monkeypatch):
    keys = []

    class FakeOpenAI:
        def __init__(self, *, api_key, **kwargs):
            keys.append(api_key)

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(llm_service.config, "LLM_API_KEY", "server-key")
    with llm_service.api_key_context("user-one-key"):
        llm_service._client()
    with llm_service.api_key_context("user-two-key"):
        llm_service._client()
    assert keys == ["user-one-key", "user-two-key"]


def test_api_error_not_swallowed(monkeypatch):
    mock(monkeypatch, [llm_service.LLMError("down")])
    with pytest.raises(llm_service.LLMError):
        enh.suggest("summary", "text")


def test_invented_numbers_guard():
    assert enh.invented_numbers("Improved speed", "Improved speed by 40%") == ["40%"]
    assert enh.invented_numbers("Managed 5 people", "Led 5 people") == []


def test_invented_skills_guard():
    assert enh.invented_skills(["Python"], "Languages: Python, Rust") == ["Rust"]


def test_apply_suggestion_does_not_mutate_original():
    d = ResumeData.model_validate({"summary": "old", "experience": [{"title": "t", "bullets": ["a"]}]})
    n = enh.apply_suggestion(enh.apply_suggestion(d, "summary", "new"), "exp:0", "- b\n- c")
    assert d.summary == "old" and n.summary == "new" and n.experience[0].bullets == ["b", "c"]


def test_analysis_sorted_by_priority(monkeypatch):
    f = lambda p: {"area": "x", "kind": "weakness", "text": "t", "priority": p}
    mock(monkeypatch, [json.dumps({"findings": [f("low"), f("high")]})])
    assert ana.analyze_resume(ResumeData()).findings[0].priority == "high"

import sys, os, zlib, re
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import numpy as np
from types import SimpleNamespace as NS
from utils.document_chunking import chunk_document
from services.rag_service import RAGService, INSUFFICIENT, EmptyDocuments
from services.retrieval_service import VectorIndex

RESUME = """Jane Doe
Summary
Backend engineer.
Experience
- Built REST APIs in Python
- Deployed services on Kubernetes
Skills
Python, SQL, Docker
Projects
Chat bot using NLP and transformers
"""
JOB = "We need a data engineer with Spark and Airflow experience. Kubernetes is a plus."


class FakeEmbedder:
    """Deterministic bag-of-words hashing embedder (no network)."""
    def __init__(self): self.calls = 0
    def embed(self, texts):
        self.calls += 1
        out = np.zeros((len(texts), 128), dtype="float32")
        for i, t in enumerate(texts):
            for w in re.findall(r"[a-z]+", t.lower()):
                out[i, zlib.crc32(w.encode()) % 128] += 1
        return out


try:
    import pydantic  # noqa: F401
except ImportError:  # sandbox without pydantic: the fake llm ignores the schema, so a stub is enough
    sys.modules["models.rag_models"] = NS(RAGAnswer=object)


def fake_llm(system, user, schema, cache):
    return NS(answer="From your documents: Python.", sufficient=True, used_sources=[1])


def test_chunk_metadata_and_sections():
    cs = chunk_document(RESUME, "resume", "cv.pdf", "s1")
    assert {c.section for c in cs} >= {"experience", "skills", "projects"}
    assert all(c.doc_name == "cv.pdf" and c.session_id == "s1" and c.doc_type == "resume" for c in cs)
    assert [c.index for c in cs] == list(range(len(cs)))


def test_job_chunks_have_no_section():
    assert chunk_document(JOB, "job_description", "j", "s1")[0].section == ""


def test_long_text_is_split_with_overlap():
    text = " ".join(f"word{i}" for i in range(400))
    cs = chunk_document(text, "job_description", "j", "s", size=200, overlap=40)
    assert len(cs) > 3 and all(len(c.text) <= 200 + 40 + 1 for c in cs)
    assert cs[1].text.split()[0] in cs[0].text      # overlap carried over


def test_bad_params_and_empty():
    assert chunk_document("   ", "resume", "x", "s") == []
    try: chunk_document("a", "resume", "x", "s", size=10, overlap=10); assert False
    except ValueError: pass


def test_retrieval_finds_relevant_chunk():
    r = RAGService("s1", FakeEmbedder(), fake_llm, min_score=0.1)
    r.sync({"cv": ("resume", RESUME), "job": ("job_description", JOB)})
    hits = r.retrieve("Spark and Airflow", {"job"})
    assert hits and hits[0][0].doc_name == "job"


def test_selected_docs_filter():
    r = RAGService("s1", FakeEmbedder(), fake_llm, min_score=0.0)
    r.sync({"cv": ("resume", RESUME), "job": ("job_description", JOB)})
    assert {c.doc_name for c, _ in r.retrieve("Kubernetes", {"cv"})} == {"cv"}


def test_session_isolation():
    emb = FakeEmbedder()
    a, b = RAGService("A", emb, fake_llm, min_score=0.0), RAGService("B", emb, fake_llm, min_score=0.0)
    a.sync({"cv": ("resume", "Secret skills: Rust Haskell Erlang developer")})
    b.sync({"cv": ("resume", RESUME)})
    # force both sessions' chunks into ONE index; session filter must still hold
    idx = VectorIndex(); chunks = a.index.chunks + b.index.chunks
    idx.build(chunks, emb.embed([c.text for c in chunks]))
    got = idx.search(emb.embed(["Rust Haskell"]), 10, "B")
    assert got and all(c.session_id == "B" for c, _ in got)
    assert not any("Haskell" in c.text for c, _ in got)


def test_ask_returns_sources_with_attribution():
    r = RAGService("s1", FakeEmbedder(), fake_llm, min_score=0.1)
    r.sync({"cv": ("resume", RESUME)})
    out = r.ask("What Python APIs did I build?", {"cv"})
    assert out["sufficient"] and out["sources"][0]["doc"] == "cv" and out["sources"][0]["text"]


def test_empty_context_skips_llm():
    called = []
    r = RAGService("s1", FakeEmbedder(), lambda *a: called.append(1), min_score=0.9)
    r.sync({"cv": ("resume", RESUME)})
    out = r.ask("zzz qqq", {"cv"})
    assert out["answer"] == INSUFFICIENT and out["sources"] == [] and not called


def test_empty_documents_error():
    try: RAGService("s", FakeEmbedder(), fake_llm).sync({"x": ("resume", "   ")}); assert False
    except EmptyDocuments: pass


def test_rebuild_only_when_documents_change_and_embeddings_cached():
    emb = FakeEmbedder(); r = RAGService("s", emb, fake_llm)
    docs = {"cv": ("resume", RESUME)}
    assert r.sync(docs) is True and r.sync(docs) is False
    n = emb.calls
    r.sync({"cv": ("resume", RESUME + "\nCertifications\nAWS Cloud Practitioner")})   # changed -> rebuild
    assert emb.calls == n + 1
    r.retrieve("Python"); r.retrieve("Python")
    assert emb.calls == n + 2                       # second identical query served from cache

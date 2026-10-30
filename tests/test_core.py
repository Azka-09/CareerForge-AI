import io, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from docx import Document
from services.resume_parser import parse_resume, ParseError
from utils.validation import validate_upload
from utils.scoring import weighted_score
from database import repository


def _docx_bytes(text):
    d = Document(); d.add_paragraph(text); b = io.BytesIO(); d.save(b); return b.getvalue()


def test_docx_extraction():
    r = parse_resume("a.docx", _docx_bytes("Jane Doe. Python developer with five years of experience in data engineering."))
    assert "Python developer" in r.text


def test_short_docx_rejected():
    with pytest.raises(ParseError):
        parse_resume("a.docx", _docx_bytes("hi"))


def test_corrupted_docx():
    with pytest.raises(ParseError):
        parse_resume("a.docx", b"PK not really a zip")


def test_validation():
    assert not validate_upload("a.txt", b"x")[0]
    assert not validate_upload("a.pdf", b"")[0]
    assert not validate_upload("a.pdf", b"nope")[0]
    assert not validate_upload("a.pdf", b"%PDF" + b"0" * 2_000_000, max_mb=1)[0]
    assert validate_upload("a.pdf", b"%PDF-1.7 ...")[0]


def test_scoring():
    assert weighted_score({"required_skills": 1, "keywords": 1}) == 100.0
    assert weighted_score({"required_skills": 0.5}) == 50.0
    assert weighted_score({}) == 0.0


def test_new_session_has_zero_counts(tmp_path):
    c = repository.counts("s1", str(tmp_path / "t.db"))
    assert all(v == 0 for v in c.values())

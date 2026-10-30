"""Text extraction from PDF/DOCX. Never logs resume content."""
import io
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)
MIN_CHARS = 50


class ParseError(Exception):
    """User-facing extraction failure."""


@dataclass
class ParsedResume:
    filename: str
    text: str
    pages: int = 1
    warnings: list[str] = field(default_factory=list)


def _pdf(data: bytes) -> tuple[str, int]:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise ParseError("PDF support requires PyMuPDF (pip install pymupdf).") from e
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        if doc.needs_pass:
            raise ParseError("This PDF is password-protected.")
        return "\n".join(p.get_text() for p in doc), len(doc)
    except ParseError:
        raise
    except Exception as e:
        logger.warning("PDF parse failed: %s", type(e).__name__)
        raise ParseError("Could not read this PDF. It may be corrupted.") from e


def _docx(data: bytes) -> tuple[str, int]:
    try:
        from docx import Document
        d = Document(io.BytesIO(data))
    except Exception as e:
        logger.warning("DOCX parse failed: %s", type(e).__name__)
        raise ParseError("Could not read this DOCX. It may be corrupted.") from e
    parts = [p.text for p in d.paragraphs]
    has_tables = bool(d.tables)
    for t in d.tables:
        for row in t.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(parts), (2 if has_tables else 1)


def parse_resume(filename: str, data: bytes) -> ParsedResume:
    is_pdf = filename.lower().endswith(".pdf")
    text, pages = _pdf(data) if is_pdf else _docx(data)
    text = text.strip()
    if len(text) < MIN_CHARS:
        if is_pdf:
            raise ParseError("No extractable text found. This looks like a scanned PDF; "
                             "OCR is required (not yet supported). Try a text-based PDF or DOCX.")
        raise ParseError("The document contains almost no text.")
    warnings = []
    if not is_pdf and " | " in text:
        warnings.append("Tables detected; some ATS parsers read tables poorly.")
    return ParsedResume(filename, text, pages, warnings)

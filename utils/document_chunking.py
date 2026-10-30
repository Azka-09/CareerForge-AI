"""Section-aware chunking with metadata. Pure Python (no AI, no network)."""
import hashlib
import re
from dataclasses import dataclass

from services.ats_analyzer import HEADINGS


@dataclass(frozen=True)
class Chunk:
    text: str
    doc_type: str      # "resume" | "job_description"
    doc_name: str
    session_id: str
    section: str       # resume section if identifiable, else ""
    index: int

    @property
    def id(self) -> str:
        return hashlib.sha1(f"{self.session_id}|{self.doc_name}|{self.index}|{self.text}".encode()).hexdigest()[:12]


def clean_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_sections(text: str, doc_type: str) -> list[tuple[str, str]]:
    if doc_type != "resume":
        return [("", text)]
    out, cur, buf = [], "", []
    for line in text.splitlines():
        hit = next((k for k, p in HEADINGS.items() if re.fullmatch(rf"\s*(?:{p})\s*:?\s*", line, re.I)), None)
        if hit:
            if "".join(buf).strip(): out.append((cur, "\n".join(buf)))
            cur, buf = hit, []
        else:
            buf.append(line)
    if "".join(buf).strip(): out.append((cur, "\n".join(buf)))
    return out


def _pieces(text: str, size: int) -> list[str]:
    units = []
    for para in (p.strip() for p in text.split("\n") if p.strip()):
        while len(para) > size:                       # hard-split long lines at a word boundary
            cut = para.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            units.append(para[:cut].strip()); para = para[cut:].strip()
        if para: units.append(para)
    return units


def _tail(text: str, overlap: int) -> str:
    if overlap <= 0 or len(text) <= overlap: return ""
    t = text[-overlap:]
    sp = t.find(" ")
    return t[sp + 1:] if sp != -1 else t


def chunk_document(text: str, doc_type: str, doc_name: str, session_id: str,
                   size: int = 800, overlap: int = 120) -> list[Chunk]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Require 0 <= overlap < size.")
    text = clean_text(text)
    chunks: list[Chunk] = []
    for section, body in split_sections(text, doc_type):
        cur = ""
        for unit in _pieces(body, size):
            if cur and len(cur) + len(unit) + 1 > size:
                chunks.append(Chunk(cur, doc_type, doc_name, session_id, section, len(chunks)))
                cur = (_tail(cur, overlap) + " " + unit).strip()
            else:
                cur = f"{cur}\n{unit}".strip() if cur else unit
        if cur.strip():
            chunks.append(Chunk(cur, doc_type, doc_name, session_id, section, len(chunks)))
    return chunks

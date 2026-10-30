"""Logging with secret/PII redaction. Resume text is never logged by the app; this is a safety net."""
import logging
import logging.handlers
import re

import config

_PATTERNS = [(re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "[REDACTED_KEY]"),
             (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[REDACTED_EMAIL]"),
             (re.compile(r"(?i)\b(password|api[_-]?key|token|secret)\b(\s*[=:]\s*)\S+"), r"\1\2[REDACTED]")]


def redact(text: str) -> str:
    for pat, rep in _PATTERNS:
        text = pat.sub(rep, text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record):          # also redacts formatted tracebacks
        return redact(super().format(record))


def setup_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_cf_configured", False):
        return
    fmt = RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handlers = [logging.StreamHandler()]
    if config.LOG_FILE:
        handlers.append(logging.handlers.RotatingFileHandler(config.LOG_FILE, maxBytes=2_000_000, backupCount=3))
    for h in handlers:
        h.setFormatter(fmt)
        root.addHandler(h)
    root.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
    root._cf_configured = True

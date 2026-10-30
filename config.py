"""Central configuration. Reads .env, real environment variables, and Streamlit secrets (hosting platforms).
Invalid numeric values never crash import; they are reported by validate()."""
import os
from dotenv import load_dotenv

load_dotenv()


def _bridge_streamlit_secrets() -> None:
    """Copy string secrets from st.secrets into the environment (without overriding real env vars)."""
    try:
        import streamlit as st
        for k in list(st.secrets):
            if isinstance(st.secrets[k], str):
                os.environ.setdefault(k, st.secrets[k])
    except Exception:  # no streamlit or no secrets file
        pass


_bridge_streamlit_secrets()
_PROBLEMS: list[str] = []


def _num(name: str, default, cast=int):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError:
        _PROBLEMS.append(f"{name} must be a number.")
        return default


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///careerforge.db").strip()
DB_PATH = DATABASE_URL[len("sqlite:///"):] if DATABASE_URL.startswith("sqlite:///") else "careerforge.db"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "")

MAX_UPLOAD_MB = _num("MAX_UPLOAD_MB", 5)
LLM_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "").strip() or "gpt-4o-mini"
LLM_TIMEOUT = _num("LLM_TIMEOUT", 60.0, float)
MAX_LLM_CHARS = _num("MAX_LLM_CHARS", 20000)
AI_DAILY_LIMIT = _num("AI_DAILY_LIMIT", 100)          # AI requests per user per UTC day; 0 = unlimited
AUTH_SESSION_HOURS = _num("AUTH_SESSION_HOURS", 8)

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai").strip().lower()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "").strip() or "text-embedding-3-small"
RAG_CHUNK_SIZE = _num("RAG_CHUNK_SIZE", 800)
RAG_CHUNK_OVERLAP = _num("RAG_CHUNK_OVERLAP", 120)
RAG_TOP_K = _num("RAG_TOP_K", 5)
RAG_MIN_SCORE = _num("RAG_MIN_SCORE", 0.25, float)


def llm_configured() -> bool:
    return bool(LLM_API_KEY)


def validate() -> tuple[list[str], list[str]]:
    """Returns (errors, warnings). Messages never contain secret values."""
    errors, warnings = list(_PROBLEMS), []
    if not DATABASE_URL.startswith("sqlite:///"):
        errors.append("DATABASE_URL must be a sqlite:/// URL. PostgreSQL is not yet supported by this version.")
    if APP_ENV not in ("development", "production"):
        errors.append("APP_ENV must be 'development' or 'production'.")
    if EMBEDDING_PROVIDER not in ("openai", "local"):
        errors.append("EMBEDDING_PROVIDER must be 'openai' or 'local'.")
    if MAX_UPLOAD_MB <= 0:
        errors.append("MAX_UPLOAD_MB must be greater than 0.")
    if not 0 <= RAG_CHUNK_OVERLAP < RAG_CHUNK_SIZE:
        errors.append("RAG_CHUNK_OVERLAP must be >= 0 and smaller than RAG_CHUNK_SIZE.")
    if AUTH_SESSION_HOURS <= 0:
        errors.append("AUTH_SESSION_HOURS must be greater than 0.")
    if not LLM_API_KEY:
        warnings.append("OPENAI_API_KEY is not set: signed-in users can provide their own key in the app.")
    if APP_ENV == "production" and not os.path.isabs(DB_PATH):
        warnings.append("DATABASE_URL uses a relative path; make sure it points to persistent storage.")
    return errors, warnings

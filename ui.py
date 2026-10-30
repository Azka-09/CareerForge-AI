from pathlib import Path
import streamlit as st

import config
from services import auth_service as auth, usage_limiter

CSS = Path(__file__).parent / "assets" / "styles.css"


def reset_session(keep: tuple = ()):
    """Wipe everything held in this browser session (used on logout/expiry so nothing leaks to the next user)."""
    for k in list(st.session_state.keys()):
        if k not in keep:
            del st.session_state[k]


def current_user() -> dict | None:
    """Validates the session token against the database on EVERY run. session_id is derived from the
    verified user id, never taken from user-controlled state."""
    from database.db import DatabaseError
    token = st.session_state.get("auth_token")
    try:
        user = auth.validate_session(token)
    except DatabaseError:
        st.error("The database is unavailable right now. Please try again shortly."); st.stop()
    if user is None:
        if token:   # a token existed but is no longer valid (expired/revoked): wipe the session
            reset_session()
            st.session_state["session_expired"] = True
        else:       # normal signed-out state: do NOT wipe, or sign-in/register form values are lost
            st.session_state.pop("user", None)
            st.session_state.pop("session_id", None)
        return None
    st.session_state.user = user
    st.session_state.session_id = auth.owner_key(user["id"])
    return user


def sign_out():
    auth.logout(st.session_state.get("auth_token"))
    reset_session()


def init_session(require_login: bool = True):
    user = current_user()
    if require_login and user is None:
        st.warning("Please sign in to continue."); st.stop()
    st.session_state.setdefault("resume", None)


def inject_css():
    st.markdown(f"<style>{CSS.read_text()}</style>", unsafe_allow_html=True)


def hero(title: str, subtitle: str):
    st.markdown(f'<div class="cf-hero"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def stat_card(label: str, value):
    st.markdown(f'<div class="cf-card"><div class="cf-stat">{value}</div>'
                f'<div class="cf-label">{label}</div></div>', unsafe_allow_html=True)


# ---------- Phase 2 helpers ----------
from services.llm_service import LLMError, LLMUnavailable  # noqa: E402


def session_cache() -> dict:
    """Per-session LLM cache: avoids duplicate requests, never shared across users."""
    return st.session_state.setdefault("llm_cache", {})


def need_resume() -> bool:
    if st.session_state.get("resume") is None:
        st.info("Upload a resume on the Resume Enhancer page first.")
        if st.button("Go to Resume Enhancer", type="primary"):
            st.switch_page("pages/2_Resume_Enhancer.py")
        return False
    return True


def ai_call(label: str, fn, *args, **kwargs):
    """Run an AI function with a spinner; show a clear error and return None on failure (no fake results)."""
    try:
        allowed = usage_limiter.consume(st.session_state.get("session_id", ""))
    except Exception:
        st.error("Could not check your AI usage limit. Please try again."); return None
    if not allowed:
        st.warning(f"You have reached today's AI limit ({config.AI_DAILY_LIMIT} requests). It resets at 00:00 UTC.")
        return None
    try:
        with st.spinner(label):
            return fn(*args, **kwargs)
    except LLMUnavailable as e:
        st.warning(f"AI unavailable: {e}")
    except LLMError as e:
        st.error(str(e))
    return None


def ensure_structured():
    """Structured resume data (AI-extracted, user-editable); None if unavailable."""
    from services.resume_analyzer import extract_structured
    if st.session_state.get("resume_data") is None and st.session_state.get("resume"):
        data = ai_call("Extracting structured data...", extract_structured,
                       st.session_state.resume.text, session_cache())
        if data is not None:
            st.session_state.resume_data = data
            st.session_state.data_ver = st.session_state.get("data_ver", 0) + 1
    return st.session_state.get("resume_data")


@st.cache_resource(show_spinner=False)
def _load_embedder():
    try:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer("all-MiniLM-L6-v2")
        return lambda texts: m.encode(list(texts), normalize_embeddings=True)
    except Exception:
        return None


def get_embedder():
    return _load_embedder()


STATUS_LABEL = {"demonstrated": "✅ Demonstrated", "mentioned": "🟡 Mentioned only",
                "needs_verification": "🔍 Needs your verification", "not_found": "⚪ Not found in resume"}


def gauge(value: float, title: str):
    import plotly.graph_objects as go
    fig = go.Figure(go.Indicator(mode="gauge+number", value=value, title={"text": title},
                                 gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#5B5FEF"},
                                        "steps": [{"range": [0, 40], "color": "#FDE2E2"},
                                                  {"range": [40, 70], "color": "#FEF3C7"},
                                                  {"range": [70, 100], "color": "#DCFCE7"}]}))
    fig.update_layout(height=260, margin=dict(l=20, r=20, t=50, b=10), paper_bgcolor="rgba(0,0,0,0)")
    return fig


def bar(names, values, title):
    import plotly.graph_objects as go
    fig = go.Figure(go.Bar(x=[v * 100 for v in values], y=names, orientation="h", marker_color="#5B5FEF"))
    fig.update_layout(title=title, height=60 + 42 * len(names), xaxis=dict(range=[0, 100], title="%"),
                      margin=dict(l=10, r=10, t=40, b=10), yaxis=dict(autorange="reversed"),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig
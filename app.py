import logging
import uuid

import streamlit as st

import config
import ui
from services import llm_service
from utils.logging_setup import setup_logging

st.set_page_config(page_title="CareerForge AI", page_icon="🛠️", layout="wide")
setup_logging()
logger = logging.getLogger("careerforge")

errors, _warnings = config.validate()
if errors:
    st.error("CareerForge AI cannot start because of configuration problems:\n\n" + "\n".join(f"- {e}" for e in errors)
             + "\n\nFix your environment variables or secrets and restart. See .env.example.")
    st.stop()

user = ui.current_user()
if user is None:
    nav = st.navigation([st.Page("pages/0_Sign_In.py", title="Sign in", icon="🔐")])
else:
    nav = st.navigation({
        "WORKSPACE": [st.Page("pages/1_Dashboard.py", title="Dashboard", icon="🏠", default=True),
                      st.Page("pages/2_Resume_Enhancer.py", title="Resume Enhancer", icon="✍️"),
                      st.Page("pages/3_ATS_Analyzer.py", title="ATS Analyzer", icon="🎯"),
                      st.Page("pages/4_Job_Matcher.py", title="Job Matcher", icon="🔗")],
        "AI CAREER TOOLS": [st.Page("pages/5_Career_Assistant.py", title="Career AI Assistant", icon="💬"),
                            st.Page("pages/6_Interview_Preparation.py", title="Interview Preparation", icon="🎤"),
                            st.Page("pages/7_Career_Roadmap.py", title="Career Roadmap", icon="🧭")],
        "ACCOUNT": [st.Page("pages/8_Privacy_and_Data.py", title="Privacy & Data", icon="🔒")],
    })
    st.sidebar.caption(f"Signed in as {user['email']}")
    if st.sidebar.button("Sign out"):
        ui.sign_out(); st.rerun()
    with st.sidebar.expander("AI API key"):
        st.caption("Only enter a key on a deployment you trust. It is sent to this server for API requests, "
                   "kept only in this session's server-side memory, and not saved to your account or database.")
        with st.form("session_api_key"):
            api_key_input = st.text_input("OpenAI API key", type="password", key="openai_api_key_input",
                                          autocomplete="off")
            use_api_key = st.form_submit_button("Use API key")
        if use_api_key:
            st.session_state["session_api_key_enabled"] = bool(api_key_input.strip())
            if api_key_input.strip():
                st.success("Your API key is active for this session.")
            else:
                st.info("Your session API key was cleared.")
        if st.session_state.get("session_api_key_enabled"):
            st.caption("Using your session API key. Clear the field and submit to remove it.")
        elif config.LLM_API_KEY:
            st.caption("Using the deployment's configured API key.")
        else:
            st.caption("Add a key to enable AI features.")
st.sidebar.markdown("### 🛠️ CareerForge AI")
st.sidebar.caption("Build a Stronger Resume. Unlock Better Opportunities.")

try:
    session_key = (st.session_state.get("openai_api_key_input")
                   if st.session_state.get("session_api_key_enabled") else None)
    with llm_service.api_key_context(session_key):
        nav.run()
except Exception:  # st.stop()/st.rerun() are BaseException subclasses and pass through untouched
    ref = uuid.uuid4().hex[:8]
    logger.exception("Unhandled error (ref %s)", ref)
    st.error(f"Something went wrong. Please try again. If it keeps happening, report reference **{ref}**.")

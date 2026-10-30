import streamlit as st
import ui
from database import repository
from services import llm_service

ui.init_session(); ui.inject_css()
ui.hero("Welcome to CareerForge AI", "Your personal workspace for smarter job applications.")
if st.button("Start New Analysis", type="primary"):
    st.switch_page("pages/2_Resume_Enhancer.py")

try:
    data = repository.counts(st.session_state.session_id)
except Exception:
    st.error("Could not read saved data. Check database settings."); data = {}
cols = st.columns(4)
for col, (k, v) in zip(cols, data.items()):
    with col: ui.stat_card(k, v)

st.subheader("Recent activity")
if not any(data.values()):
    st.info("No activity yet. Upload a resume to get started.")
if not llm_service.has_api_key():
    st.warning("No LLM API key configured. AI features are unavailable; "
               "add one in the sidebar to enable AI. Parsing and document tools still work.")

import json
import logging
import streamlit as st
import config, ui
from database import repository as repo
from services import auth_service as auth, usage_limiter

logger = logging.getLogger(__name__)
ui.init_session(); ui.inject_css()
ui.hero("Privacy & Data", "See what is stored, download it, or delete it.")
user, owner = st.session_state.user, st.session_state.session_id

st.subheader("What is stored")
st.markdown(
    "| Data | Where | Why |\n|---|---|---|\n"
    "| Email and password hash | Database | Sign-in (the password itself is never stored) |\n"
    "| Resume file and extracted text | **Not stored.** Browser session memory only; cleared on sign-out | Analysis |\n"
    "| Interview questions, your answers, AI feedback | Database | Resume sessions, reports |\n"
    "| Career roadmaps and task progress | Database | Saved progress |\n"
    "| Personal OpenAI API key | Server-side session memory only; cleared on sign-out/session end | AI requests using your provider account |\n"
    "| AI request counts per day | Database | Cost limit |\n")
st.info("When you use AI features, relevant resume or job text is sent to the configured AI provider (OpenAI by default) "
        "to generate results. Deleting data here does not delete anything the provider may retain under its own policy; "
        "check the provider's terms and your account settings.")
try:
    used = usage_limiter.used_today(owner)
    st.metric("AI requests today", f"{used}" + (f" / {config.AI_DAILY_LIMIT}" if config.AI_DAILY_LIMIT > 0 else " (no limit)"))
except Exception:
    st.caption("Usage information is unavailable.")

st.subheader("Download my data")
try:
    data = {"account": {"email": user["email"]}, **repo.export_user(owner)}
    st.download_button("⬇ Download all my data (JSON)", json.dumps(data, indent=2, default=str), "careerforge_my_data.json", "application/json")
except Exception:
    logger.exception("Export failed"); st.error("Could not prepare your export. Please try again.")

st.subheader("Delete data")
if st.button("Clear resume and chat from this session"):
    for k in ("resume", "resume_data", "report", "suggestions", "llm_cache", "matches", "rag", "chat", "job_text", "iv", "roadmap"):
        st.session_state.pop(k, None)
    st.success("Cleared.")
c1, c2 = st.columns(2)
sure = st.checkbox("I understand deletion is permanent.")
for col, label, fn in ((c1, "Delete my interview history", repo.delete_interviews), (c2, "Delete my roadmaps", repo.delete_roadmaps)):
    if col.button(label, disabled=not sure):
        try: fn(owner); st.session_state.pop("iv", None); st.session_state.pop("roadmap", None); st.success("Deleted.")
        except Exception: logger.exception("Delete failed"); st.error("Deletion failed. Please try again.")
if st.button("Delete all my saved data (keep my account)", disabled=not sure):
    try: repo.delete_all(owner); st.success("All saved data deleted.")
    except Exception: logger.exception("Delete failed"); st.error("Deletion failed. Please try again.")

st.subheader("Delete my account")
st.warning("This permanently deletes your account and all associated data.")
with st.form("delete_account"):
    pw = st.text_input("Confirm your password", type="password", autocomplete="current-password")
    typed = st.text_input("Type DELETE to confirm")
    go = st.form_submit_button("Delete my account")
if go:
    if typed != "DELETE": st.error("Type DELETE exactly to confirm.")
    elif not auth.verify_user_password(user["id"], pw): st.error("Password is incorrect.")
    else:
        try:
            auth.delete_account(user["id"]); ui.reset_session(); st.rerun()
        except Exception: logger.exception("Account deletion failed"); st.error("Account deletion failed. Please try again.")

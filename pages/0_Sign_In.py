import logging
import streamlit as st
import ui
from services import auth_service as auth

logger = logging.getLogger(__name__)
ui.inject_css()
ui.init_session(require_login=False)
ui.hero("Welcome to CareerForge AI", "Sign in to your private workspace.")
if st.session_state.pop("session_expired", False):
    st.warning("Your session expired. Please sign in again.")

tab_in, tab_up = st.tabs(["Sign in", "Create account"])
with tab_in:
    with st.form("login"):
        email = st.text_input("Email", autocomplete="email"); pw = st.text_input("Password", type="password", autocomplete="current-password")
        go = st.form_submit_button("Sign in", type="primary")
    if go:
        try:
            token, _ = auth.login(email, pw)
            ui.reset_session(); st.session_state.auth_token = token; st.rerun()
        except auth.AuthError as e: st.error(str(e))
        except Exception:
            logger.exception("Login failed unexpectedly"); st.error("Sign-in is unavailable right now. Please try again.")
    st.caption("Forgot your password? Password reset needs a configured email service, which this deployment does not have. "
               "Contact the administrator.")
with tab_up:
    with st.form("register"):
        email2 = st.text_input("Email", key="reg_email", autocomplete="email")
        pw2 = st.text_input("Password (12+ characters, with a letter and a number)", type="password", key="reg_pw", autocomplete="new-password")
        pw3 = st.text_input("Confirm password", type="password", key="reg_pw2", autocomplete="new-password")
        agree = st.checkbox("I have read how my data is stored and processed (see below).")
        go2 = st.form_submit_button("Create account", type="primary")
    if go2:
        if pw2 != pw3: st.error("Passwords do not match.")
        elif not agree: st.error("Please confirm that you have read the data notice.")
        else:
            try:
                auth.register(email2, pw2)
                token, _ = auth.login(email2, pw2)
                ui.reset_session(); st.session_state.auth_token = token; st.rerun()
            except auth.AuthError as e: st.error(str(e))
            except Exception:
                logger.exception("Registration failed unexpectedly"); st.error("Could not create the account. Please try again.")
with st.expander("How your data is handled"):
    st.markdown("- Resume files are read in memory and **not saved to disk**; extracted text lives only in your browser session.\n"
                "- Interview answers, feedback, roadmaps and progress are saved in the app database under your account.\n"
                "- When you use AI features, relevant text is sent to the configured AI provider.\n"
                "- You can export or delete your data any time under **Privacy & Data**.")

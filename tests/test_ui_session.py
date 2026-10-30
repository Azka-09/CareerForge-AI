"""Regression: signed-out page runs must not wipe form widget state (Create account bug).
Uses a tiny fake `streamlit` so it runs anywhere."""
import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class _State(dict):
    def __getattr__(self, k): return self.get(k)
    def __setattr__(self, k, v): self[k] = v


def _load_ui(state):
    fake = types.ModuleType("streamlit")
    fake.session_state = state
    fake.cache_resource = lambda **kw: (lambda f: f)
    fake.error = lambda *a, **k: None
    fake.stop = lambda: (_ for _ in ()).throw(RuntimeError("stop"))
    saved = {k: sys.modules.get(k) for k in ("streamlit", "ui")}
    sys.modules["streamlit"] = fake; sys.modules.pop("ui", None)
    import ui
    return ui, saved


def _restore(saved):
    for k, v in saved.items():
        if v is None: sys.modules.pop(k, None)
        else: sys.modules[k] = v


def test_signed_out_run_keeps_form_values():
    state = _State(reg_email="a@example.com", reg_pw="secret-password-1", reg_pw2="secret-password-1")
    ui, saved = _load_ui(state)
    try:
        ui.auth.validate_session = lambda token: None
        assert ui.current_user() is None
        assert state["reg_email"] == "a@example.com" and state["reg_pw"] == "secret-password-1"
        assert "session_expired" not in state
    finally: _restore(saved)


def test_expired_token_wipes_session_and_flags_it():
    state = _State(auth_token="stale", resume="private text", chat=["x"])
    ui, saved = _load_ui(state)
    try:
        ui.auth.validate_session = lambda token: None
        assert ui.current_user() is None
        assert "resume" not in state and "chat" not in state and "auth_token" not in state
        assert state["session_expired"] is True
    finally: _restore(saved)


def test_valid_token_sets_owner_from_verified_user_not_state():
    state = _State(auth_token="good", session_id="u999")          # forged id in state must be overwritten
    ui, saved = _load_ui(state)
    try:
        ui.auth.validate_session = lambda token: {"id": 5, "email": "a@example.com"}
        assert ui.current_user()["id"] == 5
        assert state["session_id"] == "u5"
    finally: _restore(saved)

# CareerForge AI

Streamlit app for resume analysis, ATS-style checks, job matching, a RAG career assistant, interview practice and a learning roadmap, with per-user accounts.

> **Status:** Phases 1-3 and the Phase 5 security/ops work are implemented. **Phase 4 features are not built**: Resume Builder / exports / resume versions, Application Tracker and analytics, Skill Gap page. **PostgreSQL is not supported yet** (SQLite only). See *Known limitations*.

## Features
- Sign-in with email + password (Argon2id, server-side sessions, lockout after repeated failures)
- Resume upload (PDF/DOCX), structured extraction, analysis, rewrite suggestions (accept/reject/edit/regenerate)
- ATS compatibility **estimate** (heuristic, not an official ATS score) and job matching with transparent weights
- Career AI Assistant (RAG with source excerpts), Interview Preparation (feedback + PDF/Markdown report), Career Roadmap (saved progress)
- Privacy & Data page: what is stored, JSON export, deletion, account deletion
- Per-user daily AI request limit, redacted logging, health check

## Tech stack
Python 3.12, Streamlit, SQLite (versioned migrations), OpenAI API (chat + embeddings, or local sentence-transformers), FAISS (numpy fallback), Pydantic, scikit-learn, Plotly, ReportLab, PyMuPDF, python-docx, argon2-cffi.

## Project structure
```
app.py                  entry point: config check, auth gate, navigation, error guard
config.py               env/secrets loading + validate()
health.py               health check (python health.py)
pages/                  Streamlit pages (0_Sign_In ... 8_Privacy_and_Data)
services/               auth, llm, rag, embeddings, retrieval, interview, roadmap, matching, usage limiter
database/               db.py (migrations), repository.py (all queries are owner-scoped)
models/ utils/ tests/   Pydantic models, helpers, pytest suite
.streamlit/config.toml  theme + hardened server settings
Dockerfile, .github/workflows/ci.yml
```

## Local setup (Windows)
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
notepad .env
streamlit run app.py
```
macOS/Linux: `source .venv/bin/activate` and `cp .env.example .env`. Use Python 3.12.
`sentence-transformers` installs PyTorch (large). To skip it, set `EMBEDDING_PROVIDER=openai`; semantic matching then falls back to TF-IDF only if the package is absent.

## Configuration
Copy `.env.example` to `.env` (never commit it). On hosting platforms put server-wide settings in the platform's secret store; Streamlit `secrets.toml` string values are also read. Signed-in users can enter a personal OpenAI API key in the **AI API key** section of the sidebar. That key takes precedence over the server key and stays only in that Streamlit session's server-side memory; it is not saved to the account or database and is cleared on sign-out or when the session ends. Without a personal key, the app uses `OPENAI_API_KEY` from its server configuration, if present.

The default chat and embedding models are `gpt-4o-mini` and `text-embedding-3-small`; override them with `LLM_MODEL` and `EMBEDDING_MODEL` if needed. OpenAI API usage is billed to the account that owns the active key.

**Cost control:** `AI_DAILY_LIMIT` caps AI requests per user per UTC day (counted when a request starts, including cache hits; deleting your data does not reset it). Users see their count under Privacy & Data. Monitor actual spend in your AI provider's usage dashboard and set a provider-side budget as well.

## Database and migrations
SQLite file from `DATABASE_URL` (default `sqlite:///careerforge.db`). Migrations are numbered, additive and idempotent, applied automatically on first connect, recorded in `schema_migrations`, and never drop or reset data (databases from earlier phases are upgraded in place). Verify with `python health.py` (expects `schema_version` 4). **Back up the `.db` file before upgrading.**
PostgreSQL: not implemented. It would require porting the query layer (placeholders, `lastrowid`, upserts) to SQLAlchemy/Alembic and testing against a real server, which could not be done or verified in this environment.

## Tests
```
python -m pytest            # add --cov for coverage
ruff check .
python health.py
```
AI calls are mocked; no API key or network is needed.

## Deployment
**Recommended now: Docker on a host with a persistent volume** (Render, Fly.io, Railway, a VPS), because data lives in a SQLite file.
```
docker build -t careerforge .
docker run -p 8501:8501 -v careerforge-data:/data --env-file .env careerforge
```
The image sets `DATABASE_URL=sqlite:////data/careerforge.db` and runs as a non-root user; mount `/data` as persistent storage and set secrets via the platform. Put the app behind HTTPS (platform proxy or reverse proxy); sign-in credentials are sent from the browser to the server.
**Streamlit Community Cloud:** works for demos only. Its disk is not persistent, so accounts and saved data can disappear on restart. Use it for production only after a hosted database is supported.
**Updating:** pull the new code, rebuild/restart; migrations apply automatically. Check `python health.py` afterwards.
CI (`.github/workflows/ci.yml`) runs compile check, ruff, a secret grep, pytest with coverage and the health check, with no API keys. A dependency audit job is report-only. There is no auto-deploy job.

## Logs and troubleshooting
Logs go to the console; set `LOG_FILE` for a rotating file. Emails, API keys and password/token values are redacted. Users see only a reference id on unexpected errors: search the logs for that id.
- *"cannot start because of configuration problems"*: fix the listed variable in `.env`/secrets.
- *AI features show "unavailable"*: enter an OpenAI API key in the sidebar, or set `OPENAI_API_KEY` in server configuration. The default models are `gpt-4o-mini` and `text-embedding-3-small`.
- *"database error"*: check the path in `DATABASE_URL` is writable, then run `python health.py`.
- *Signed out unexpectedly*: sessions last `AUTH_SESSION_HOURS`, and a browser refresh ends the Streamlit session (the token is held in server-side session state, not a cookie).
- *Locked out*: wait 15 minutes after 5 failed attempts.

## Security and privacy notes
- Passwords: Argon2id (stdlib scrypt fallback); tokens are random and stored only as SHA-256 hashes; a new token is issued on every login; sessions are validated against the database on every page run; unknown-email and wrong-password errors are identical.
- Every query for user-owned data is filtered by an owner key derived from the verified session; cross-user read/modify/delete attempts are covered by tests.
- Resume files are processed in memory and never written to disk; extracted text stays in the session until sign-out. Saved: interview answers/feedback, roadmaps, progress, usage counts.
- Personal OpenAI API keys stay in session memory only; users are responsible for any provider charges incurred with their key.
- Document text sent to AI is wrapped as untrusted content; the assistant refuses to answer beyond retrieved excerpts.
- AI processing happens at the configured provider; deleting data here does not delete anything the provider retains. Review the provider's data policy before real use. This project makes no legal-compliance claims.

## Known limitations
- Phase 4 features are missing (see top). SQLite only; single-instance deployment.
- No password reset (needs a configured email service) and no email verification or MFA.
- Login token is not persisted in a cookie, so a page reload requires signing in again.
- Scanned PDFs are not OCR'd. No screenshots are included because the UI could not be run in the development sandbox.
- Not verified in the development sandbox: the Streamlit pages, the Argon2 path, FAISS, the Docker build, and the CI workflow execution (see the handover report).

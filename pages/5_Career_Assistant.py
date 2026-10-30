import streamlit as st
import ui
from services.embedding_service import get_embedder
from services.rag_service import RAGService
from services.llm_service import LLMError, LLMUnavailable

ui.init_session(); ui.inject_css()
ui.hero("Career AI Assistant", "Ask questions grounded in your resume and job descriptions, with the source excerpts shown.")
if not ui.need_resume(): st.stop()
st.caption("Selected document text is embedded and sent to your configured AI provider to answer questions. "
           "Answers can be wrong; check them against the excerpts.")

# ---- available documents (session-scoped) ----
r = st.session_state.resume
docs = {f"Resume: {r.filename}": ("resume", r.text)}
jd = st.session_state.get("job_text", "")
if len(jd.strip()) >= 40: docs["Job: current job description"] = ("job_description", jd)
for m in st.session_state.get("matches", []):
    if m["jd"].strip() != jd.strip(): docs[f"Job: {m['label']}"] = ("job_description", m["jd"])
with st.expander("Add a job description"):
    new_jd = st.text_area("Paste job description", height=120, key="assistant_jd")
    if st.button("Use this job description") and len(new_jd.strip()) >= 40:
        st.session_state.job_text = new_jd; st.rerun()
selected = st.multiselect("Documents the assistant may use", list(docs), default=list(docs))

# ---- index (rebuilt only when document content changes) ----
if "rag" not in st.session_state:
    try:
        st.session_state.rag = RAGService(st.session_state.session_id, get_embedder())
    except LLMUnavailable as e:
        st.warning(f"AI unavailable: {e}"); st.stop()
rag: RAGService = st.session_state.rag
try:
    with st.spinner("Indexing documents..."):
        rebuilt = rag.sync(docs)
except LLMError as e:
    st.error(str(e)); st.stop()

chat = st.session_state.setdefault("chat", [])
left, right = st.columns([5, 1])
if right.button("🗑 Clear chat"): st.session_state.chat = []; st.rerun()

if not chat:
    st.markdown("**Try a question:**")
    qs = ["What are the strongest parts of my resume?", "Which of my projects best match this job?",
          "What technical questions could an interviewer ask me?", "Which skills should I improve?",
          "How can I explain my previous experience?", "Am I a good match for this position?"]
    cols = st.columns(3)
    for i, q in enumerate(qs):
        if cols[i % 3].button(q, key=f"sq{i}", use_container_width=True): st.session_state.pending_q = q; st.rerun()

for m in chat:
    with st.chat_message(m["role"], avatar="🧑" if m["role"] == "user" else "🛠️"):
        st.markdown(m["content"])
        if m.get("sources"):
            with st.expander(f"Sources ({len(m['sources'])})"):
                for s in m["sources"]:
                    st.markdown(f"**[{s['n']}] {s['doc']}**" + (f" · {s['section']}" if s["section"] else "") + f" · similarity {s['score']}")
                    st.caption(s["text"])
        if m.get("insufficient"): st.caption("⚠️ The documents did not contain enough information.")

q = st.chat_input("Ask about your resume or the job...") or st.session_state.pop("pending_q", None)
if q:
    if not selected: st.error("Select at least one document.")
    else:
        hist = [{"role": m["role"], "content": m["content"]} for m in chat]
        chat.append({"role": "user", "content": q})
        out = ui.ai_call("Searching your documents...", rag.ask, q, set(selected), hist)
        if out is None: chat.pop()
        else: chat.append({"role": "assistant", "content": out["answer"], "sources": out["sources"], "insufficient": not out["sufficient"]})
        st.rerun()

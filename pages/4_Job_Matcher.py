import streamlit as st
import pandas as pd
import ui
from models.resume_models import JobRequirements
from services.llm_service import structured, doc
from services.resume_analyzer import analyze_resume
from services import job_matcher as jm
from utils.scoring import DEFAULT_WEIGHTS

ui.init_session(); ui.inject_css()
ui.hero("Job Matcher", "Compare your resume with a job description using keywords, semantic similarity and AI analysis.")
if not ui.need_resume(): st.stop()

c1, c2 = st.columns(2)
title = c1.text_input("Job title (optional)"); company = c2.text_input("Company (optional)")
jd = st.text_area("Job description", st.session_state.get("job_text", ""), height=200)
st.session_state.job_text = jd
with st.expander("Scoring weights (configurable)"):
    w = {k: st.slider(k.replace("_", " ").title(), 0, 100, int(v * 100)) for k, v in DEFAULT_WEIGHTS.items()}
    st.caption("Weights are normalised. Match % is an estimate, not an employer's score.")

if st.button("Analyze match", type="primary"):
    if len(jd.strip()) < 40:
        st.error("Paste a fuller job description (at least a few sentences).")
    else:
        data = ui.ensure_structured()
        req = ui.ai_call("Reading job description...", structured,
                         "Extract job requirements. Only include what the text explicitly states or clearly implies.",
                         doc("job_description", jd), JobRequirements, ui.session_cache())
        if req is not None:
            embed = ui.get_embedder()
            out = jm.match(data.model_dump() if data else None, st.session_state.resume.text, req.model_dump(), jd,
                           {k: v / 100 for k, v in w.items()}, embed)
            out.update(label=f"{company or 'Job'} · {title or req.title or 'Untitled'}", req=req.model_dump(),
                       semantic="Sentence Transformers" if embed else "TF-IDF similarity (install sentence-transformers for embeddings)",
                       structured=data is not None, jd=jd)
            st.session_state.setdefault("matches", []).append(out)

matches = st.session_state.get("matches", [])
if not matches:
    st.info("Paste a job description and click Analyze match."); st.stop()
labels = [f"{i+1}. {m['label']} ({m['score']}%)" for i, m in enumerate(matches)]
m = matches[st.selectbox("Result", range(len(matches)), index=len(matches) - 1, format_func=lambda i: labels[i])]
if not m["structured"]: st.warning("Structured resume data was unavailable, so skills can only be marked 'mentioned', never 'demonstrated'.")

a, b = st.columns([1, 2])
a.plotly_chart(ui.gauge(m["score"], "Estimated job match"), use_container_width=True)
b.plotly_chart(ui.bar([k.replace("_", " ").title() for k in m["components"]], list(m["components"].values()), "Score components"), use_container_width=True)
st.caption(f"Semantic method: {m['semantic']} · Keywords from: {m['keywords_source']}")

def table(rows):
    if not rows: st.caption("None listed."); return
    st.dataframe(pd.DataFrame([{"Skill": r["skill"], "Status": ui.STATUS_LABEL[r["status"]], "Evidence": r["evidence"]} for r in rows]),
                 use_container_width=True, hide_index=True)

t1, t2, t3, t4 = st.tabs(["Required skills", "Preferred skills", "Projects & experience", "Recommendations"])
with t1:
    table(m["required"])
    st.caption("'Not found' means no matching text was detected. It does not prove you lack the skill; add it only if it is true and you can show evidence.")
with t2: table(m["preferred"])
with t3:
    if m["projects"]:
        st.plotly_chart(ui.bar([p["name"] or "Untitled" for p in m["projects"]], [p["relevance"] for p in m["projects"]], "Project relevance"), use_container_width=True)
    else: st.info("No projects found in your structured resume.")
    st.metric("Experience alignment", f"{int(m['components']['experience']*100)}%")
    r = m["req"]
    for lbl, key in (("Experience requirements", "experience_requirements"), ("Education", "education_requirements"), ("Certifications", "certifications")):
        if r[key]: st.markdown(f"**{lbl}:** " + "; ".join(r[key]))
    st.markdown("**Keywords found:** " + (", ".join(m["keywords_found"]) or "none")); st.markdown("**Keywords not found:** " + (", ".join(m["keywords_missing"]) or "none"))
with t4:
    if st.button("Generate recommendations"):
        data = st.session_state.get("resume_data")
        if data is None: st.warning("Extract structured data first.")
        else:
            rep = ui.ai_call("Preparing recommendations...", analyze_resume, data, m["jd"], ui.session_cache())
            if rep is not None: st.session_state.setdefault("job_recs", {})[m["label"]] = rep
    rep = st.session_state.get("job_recs", {}).get(m["label"])
    if rep:
        for f in [x for x in rep.findings if x.kind == "weakness"]:
            st.markdown(f"**{f.priority.title()} · {f.area}:** {f.text}" + (f"\n\n*Suggestion:* {f.suggestion}" if f.suggestion else ""))
if len(matches) > 1:
    st.subheader("Compare jobs")
    st.dataframe(pd.DataFrame([{"Job": x["label"], "Match %": x["score"]} for x in matches]), hide_index=True)

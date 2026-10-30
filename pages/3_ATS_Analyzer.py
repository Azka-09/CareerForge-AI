import streamlit as st
import ui
from services import ats_analyzer as ats

ui.init_session(); ui.inject_css()
ui.hero("ATS Analyzer", "Estimate how machine-readable your resume is, and how well it aligns with a job.")
st.info("This is an **estimate** from transparent heuristics. It is not an official ATS score; real systems parse and rank differently.")
if not ui.need_resume(): st.stop()

jd = st.text_area("Job description (optional, enables keyword alignment)", st.session_state.get("job_text", ""), height=140)
st.session_state.job_text = jd
keywords = None
if jd.strip() and st.checkbox("Use AI to extract job keywords (otherwise basic frequency extraction)"):
    from services.job_matcher import extract_keywords_basic as _b  # noqa
    from models.resume_models import JobRequirements
    from services.llm_service import structured, doc
    req = ui.ai_call("Reading job description...", structured,
                     "Extract job requirements. Only include what the text states.", doc("job_description", jd),
                     JobRequirements, ui.session_cache())
    if req: keywords = req.keywords or None

res = ats.analyze(st.session_state.resume.text, keywords, jd)
c1, c2 = st.columns([1, 2])
c1.plotly_chart(ui.gauge(res["score"], "Estimated compatibility"), use_container_width=True)
cats = res["categories"]
c2.plotly_chart(ui.bar([c["name"] for c in cats], [c["score"] for c in cats], "Category scores"), use_container_width=True)
badge = {"detected": "🔬 Directly detected", "estimated": "📐 Estimated"}
for c in cats:
    with st.container(border=True):
        st.markdown(f"**{c['name']}** · {int(c['score']*100)}% · {badge[c['source']]}")
        st.progress(c["score"]); st.caption(c["explanation"])
        for i in c["issues"]: st.warning(i)
        if not c["issues"]: st.success("No issues detected.")
with st.expander("Methodology"):
    st.write("Each category is scored 0-100% from rules applied to the extracted text, then combined with fixed weights:")
    st.table({"Category": [k.title() for k in ats.ATS_WEIGHTS], "Weight": [f"{int(v*100)}%" for v in ats.ATS_WEIGHTS.values()]})
    st.caption("Fonts, images, headers/footers and true column layout cannot be detected from extracted text. "
               "Recommendations come from these rules, not from an AI model.")

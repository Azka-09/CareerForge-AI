import streamlit as st
import config, ui
from models.resume_models import ResumeData, Experience, Project, Education, PersonalInfo
from services.resume_parser import parse_resume, ParseError
from services.resume_analyzer import analyze_resume
from services import resume_enhancer as enh
from utils.validation import validate_upload

ui.init_session(); ui.inject_css()
ui.hero("Resume Enhancer", "Extract, analyze and improve your resume. AI suggestions never overwrite your original.")
st.caption("Uploaded files are processed in memory for this session. AI steps send resume text to your configured LLM provider.")

f = st.file_uploader("Upload resume (PDF or DOCX)", type=["pdf", "docx"])
if f is not None and st.session_state.get("resume_name") != (f.name, f.size):
    ok, msg = validate_upload(f.name, f.getvalue(), config.MAX_UPLOAD_MB)
    if not ok:
        st.error(msg)
    else:
        try:
            with st.spinner("Extracting text..."):
                st.session_state.resume = parse_resume(f.name, f.getvalue())
            # new document: drop everything derived from the previous one
            for k in ("resume_data", "report", "suggestions", "llm_cache", "matches"):
                st.session_state.pop(k, None)
            st.session_state.resume_name = (f.name, f.size)
        except ParseError as e:
            st.session_state.resume = None
            st.error(str(e))

r = st.session_state.resume
if not r:
    st.info("Upload a resume to begin."); st.stop()
st.success(f"Extracted {len(r.text):,} characters from {r.filename}")
for w in r.warnings: st.warning(w)

tab_data, tab_an, tab_enh = st.tabs(["📄 Extracted data", "🔎 Analysis", "✨ Enhance"])
ver = st.session_state.get("data_ver", 0)

with tab_data:
    with st.expander("Original extracted text"):
        st.text_area("Original", r.text, height=240, disabled=True, label_visibility="collapsed")
    if st.session_state.get("resume_data") is None:
        st.write("Use AI to organise the text into editable sections. Missing information stays empty.")
        if st.button("Extract structured data", type="primary"):
            ui.ensure_structured(); st.rerun()
    else:
        d: ResumeData = st.session_state.resume_data
        k = lambda n: f"{n}_{ver}"
        c1, c2 = st.columns(2)
        name = c1.text_input("Name", d.personal.name, key=k("name")); email = c2.text_input("Email", d.personal.email, key=k("email"))
        phone = c1.text_input("Phone", d.personal.phone, key=k("phone")); loc = c2.text_input("Location", d.personal.location, key=k("loc"))
        summary = st.text_area("Professional summary", d.summary, key=k("sum"))
        skills = st.text_area("Technical skills (comma-separated)", ", ".join(d.skills), key=k("skills"))
        exps = []
        for i, e in enumerate(d.experience):
            with st.expander(f"Experience: {e.title or 'Untitled'} @ {e.company}"):
                t = st.text_input("Title", e.title, key=k(f"et{i}")); co = st.text_input("Company", e.company, key=k(f"ec{i}"))
                dt = st.text_input("Dates", e.dates, key=k(f"ed{i}"))
                b = st.text_area("Bullets (one per line)", "\n".join(e.bullets), key=k(f"eb{i}"))
                exps.append(Experience(title=t, company=co, dates=dt, bullets=[x.strip() for x in b.splitlines() if x.strip()]))
        projs = []
        for i, p in enumerate(d.projects):
            with st.expander(f"Project: {p.name or 'Untitled'}"):
                n = st.text_input("Name", p.name, key=k(f"pn{i}")); ds = st.text_area("Description", p.description, key=k(f"pd{i}"))
                tc = st.text_input("Technologies", ", ".join(p.technologies), key=k(f"pt{i}"))
                projs.append(Project(name=n, description=ds, technologies=[x.strip() for x in tc.split(",") if x.strip()]))
        edu = st.text_area("Education (one per line: degree, institution, dates)",
                           "\n".join(", ".join(x for x in (e.degree, e.institution, e.dates) if x) for e in d.education), key=k("edu"))
        certs = st.text_area("Certifications (one per line)", "\n".join(d.certifications), key=k("certs"))
        if st.button("Save changes", type="primary"):
            parsed_edu = []
            for ln in edu.splitlines():
                if ln.strip():
                    parts = [x.strip() for x in ln.split(",")] + ["", ""]
                    parsed_edu.append(Education(degree=parts[0], institution=parts[1], dates=parts[2]))
            st.session_state.resume_data = ResumeData(
                personal=PersonalInfo(name=name, email=email, phone=phone, location=loc, links=d.personal.links),
                summary=summary, skills=[s.strip() for s in skills.split(",") if s.strip()], experience=exps,
                projects=projs, education=parsed_edu, certifications=[c.strip() for c in certs.splitlines() if c.strip()])
            st.success("Saved.")

with tab_an:
    jd = st.text_area("Target job description (optional, enables relevance analysis)", st.session_state.get("job_text", ""), height=120)
    st.session_state.job_text = jd
    if st.button("Analyze resume", type="primary"):
        data = ui.ensure_structured()
        if data is not None:
            rep = ui.ai_call("Analyzing resume...", analyze_resume, data, jd, ui.session_cache())
            if rep is not None: st.session_state.report = rep
    rep = st.session_state.get("report")
    if rep is None:
        st.info("Run the analysis to see strengths, weaknesses and prioritized suggestions.")
    else:
        s = [x for x in rep.findings if x.kind == "strength"]; w = [x for x in rep.findings if x.kind == "weakness"]
        m1, m2, m3 = st.columns(3); m1.metric("Strengths", len(s)); m2.metric("Weaknesses", len(w))
        m3.metric("High priority", sum(x.priority == "high" for x in w))
        st.subheader("Strengths")
        for x in s: st.success(f"**{x.area}**: {x.text}")
        st.subheader("Weaknesses and suggestions")
        icon = {"high": "🔴", "medium": "🟠", "low": "🟢"}
        for x in w:
            with st.expander(f"{icon[x.priority]} {x.priority.title()} · {x.area}"):
                st.write(x.text)
                if x.suggestion: st.markdown(f"**Suggestion:** {x.suggestion}")
        if rep.missing_sections: st.warning("Missing sections: " + ", ".join(rep.missing_sections))
        st.caption("AI feedback is advisory and may be incorrect.")

with tab_enh:
    d = st.session_state.get("resume_data")
    if d is None:
        st.info("Extract structured data first (Extracted data tab).")
    else:
        opts = {"Professional summary": "summary", "Technical skills": "skills"}
        opts.update({f"Experience: {e.title or i+1}": f"exp:{i}" for i, e in enumerate(d.experience)})
        opts.update({f"Project: {p.name or i+1}": f"proj:{i}" for i, p in enumerate(d.projects)})
        c1, c2 = st.columns([3, 2])
        label = c1.selectbox("Section", list(opts)); mode = c2.radio("Mode", ["improve", "grammar"], horizontal=True)
        key = opts[label]

        def original_for(key):
            if key == "summary": return d.summary
            if key == "skills": return ", ".join(d.skills)
            if key.startswith("exp:"): return "\n".join(d.experience[int(key[4:])].bullets)
            return d.projects[int(key[5:])].description

        def generate(nonce):
            kind = {"summary": "summary", "skills": "skills"}.get(key, "experience" if key.startswith("exp:") else "project")
            ctx = st.session_state.get("job_text", "")
            res = ui.ai_call("Generating suggestion...", enh.suggest, kind, original_for(key), mode, ctx, nonce, ui.session_cache())
            if res is not None:
                st.session_state.setdefault("suggestions", {})[key] = {
                    "original": original_for(key), "improved": res.improved, "needs_info": res.needs_info,
                    "nonce": nonce, "editing": False}

        sugg = st.session_state.get("suggestions", {})
        if not original_for(key).strip():
            st.info("This section is empty. Add content first; the AI will not invent it.")
        elif st.button("Generate suggestion", type="primary"):
            generate(0); st.rerun()
        s = sugg.get(key)
        if s:
            a, b = st.columns(2)
            a.markdown("**Original**"); a.text_area("o", s["original"], height=200, disabled=True, label_visibility="collapsed", key=f"o_{key}_{s['nonce']}")
            b.markdown("**Suggested**")
            if s["editing"]:
                s["improved"] = b.text_area("e", s["improved"], height=200, label_visibility="collapsed", key=f"e_{key}_{s['nonce']}")
            else:
                b.text_area("i", s["improved"], height=200, disabled=True, label_visibility="collapsed", key=f"i_{key}_{s['nonce']}")
            nums = enh.invented_numbers(s["original"], s["improved"])
            if nums: st.warning(f"This suggestion contains numbers not in your original: {', '.join(nums)}. Verify or remove them.")
            if key == "skills":
                ns = enh.invented_skills(d.skills, s["improved"])
                if ns: st.warning(f"Skills not in your original list: {', '.join(ns)}. Reject or remove if untrue.")
            for q in s["needs_info"]: st.info(f"To improve this further, tell us: {q}")
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("✅ Accept"):
                st.session_state.resume_data = enh.apply_suggestion(d, key, s["improved"])
                st.session_state.data_ver = ver + 1; sugg.pop(key); st.rerun()
            if b2.button("✖ Reject"):
                sugg.pop(key); st.rerun()
            if b3.button("✏️ Save edit" if s["editing"] else "✏️ Edit"):
                s["editing"] = not s["editing"]; st.rerun()
            if b4.button("🔄 Regenerate"):
                generate(s["nonce"] + 1); st.rerun()
            st.caption("Review every suggestion for accuracy before accepting. Your original is only changed when you click Accept.")

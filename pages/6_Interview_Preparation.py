import streamlit as st
import ui
from database import repository as repo
from services import interview_service as isvc, interview_evaluator as ev

ui.init_session(); ui.inject_css()
ui.hero("Interview Preparation", "Practise with questions tailored to your resume and target job. Feedback is advisory and may be incorrect.")
if not ui.need_resume(): st.stop()
sid = st.session_state.session_id
iv = st.session_state.get("iv")


def db(fn, *a):
    try: return fn(*a)
    except Exception:
        st.error("Could not access saved data. Check database settings."); return None


# ------------------------------------------------ setup
if iv is None:
    c1, c2 = st.columns(2)
    title = c1.text_input("Target job title"); company = c2.text_input("Company (optional)")
    category = c1.selectbox("Interview category", isvc.CATEGORIES, format_func=str.title)
    difficulty = c2.selectbox("Difficulty", isvc.DIFFICULTY, format_func=str.title)
    n = st.slider("Number of questions", 1, isvc.MAX_Q, 5)
    jd = st.text_area("Job description (recommended)", st.session_state.get("job_text", ""), height=130)
    st.session_state.job_text = jd
    st.caption("Your answers and feedback are saved to this app's local database so you can resume later. You can delete them below.")
    if st.button("Start interview", type="primary"):
        if not title.strip(): st.error("Enter a target job title.")
        else:
            data = ui.ensure_structured()
            if data is not None:
                qs = ui.ai_call("Preparing questions...", isvc.generate_questions, data.model_dump_json(), jd, title, company,
                                category, difficulty, n, ui.session_cache())
                if qs:
                    meta = {"job_title": title, "company": company, "category": category, "difficulty": difficulty}
                    iid = db(repo.create_interview, sid, meta, qs)
                    if iid:
                        st.session_state.iv = {"id": iid, "meta": meta, "items": [{**q, "answer": "", "evaluation": None} for q in qs], "pos": 0, "done": False}
                        st.rerun()
    saved = db(repo.list_interviews, sid) or []
    if saved:
        st.subheader("Saved interviews")
        for s in saved:
            a, b = st.columns([4, 1])
            a.write(f"**{s['job_title']}** · {s['category']} · {s['difficulty']} · {s['status'].replace('_', ' ')} · {s['created_at']}")
            if b.button("Open", key=f"open{s['id']}"):
                loaded = db(repo.load_interview, sid, s["id"])
                if loaded:
                    st.session_state.iv = {**loaded, "pos": 0, "done": s["status"] == "completed"}; st.rerun()
        if st.button("Delete all saved interviews"): db(repo.delete_interviews, sid); st.rerun()
    st.stop()

items, pos, meta = iv["items"], iv["pos"], iv["meta"]

# ------------------------------------------------ report
if iv["done"]:
    rep = ev.build_report(items)
    st.subheader("Interview performance report")
    if rep["overall"] is None:
        st.info("No answers were evaluated. Go back and request feedback on at least one answer.")
    else:
        m1, m2, m3 = st.columns(3); m1.metric("Overall", f"{rep['overall']}/10")
        m2.metric("Evaluated", f"{rep['evaluated']}/{rep['total']}"); m3.metric("Unanswered", len(rep["unanswered"]))
        cats = rep["by_category"]
        st.plotly_chart(ui.bar([c.title() for c in cats], [v / 10 for v in cats.values()], "Average score by category (x10 %)"), use_container_width=True)
        st.markdown("**Strong answers:** " + (", ".join(f"Q{n+1}" for n in rep["strong"]) or "none yet"))
        st.markdown("**Needs improvement:** " + (", ".join(f"Q{n+1}" for n in rep["needs_work"]) or "none"))
        st.markdown("**Topics to prepare further:** " + (", ".join(rep["topics"]) or "none identified"))
    md = ev.report_markdown(rep, items, meta)
    d1, d2 = st.columns(2)
    d1.download_button("⬇ Download report (Markdown)", md, "interview_report.md", "text/markdown")
    try: d2.download_button("⬇ Download report (PDF)", ev.report_pdf(md), "interview_report.pdf", "application/pdf")
    except Exception: d2.warning("PDF export failed; use the Markdown report.")
    with st.expander("Review all questions and answers"):
        for n, i in enumerate(items):
            st.markdown(f"**Q{n+1}. {i['question']}**"); st.write(i["answer"] or "_not answered_")
            if i["evaluation"]: st.caption(f"Score {i['evaluation']['score']}/10")
    if st.button("Back to interview list", type="primary"): st.session_state.iv = None; st.rerun()
    st.stop()

# ------------------------------------------------ session
p = ev.progress(items)
st.progress(p["pct"] / 100, text=f"{p['answered']} of {p['total']} answered · {p['evaluated']} evaluated")
q = items[pos]
st.markdown(f"### Question {pos + 1} of {len(items)}  ·  {q['category'].title()}")
st.markdown(f"**{q['question']}**")
if q["category"] == "behavioral": st.info("Tip: structure your answer with STAR: Situation, Task, Action, Result. Only describe things you actually did.")
ans = st.text_area("Your answer", q["answer"], height=180, key=f"ans_{iv['id']}_{pos}")
b1, b2 = st.columns(2)
if b1.button("💾 Save answer"):
    q["answer"] = ans; db(repo.save_answer, sid, iv["id"], pos, ans, q["evaluation"]); st.toast("Saved")
if b2.button("🎯 Get feedback", type="primary"):
    err = ev.validate_answer(ans)
    if err: st.error(err)
    else:
        data = st.session_state.get("resume_data")
        out = ui.ai_call("Evaluating your answer...", ev.evaluate, q, ans, data.model_dump_json() if data else st.session_state.resume.text,
                         st.session_state.get("job_text", ""), ui.session_cache())
        if out:
            q["answer"], q["evaluation"] = ans, out
            db(repo.save_answer, sid, iv["id"], pos, ans, out); st.rerun()
e = q["evaluation"]
if e:
    st.metric("Score", f"{e['score']}/10")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Strengths**"); [st.success(x) for x in e["strengths"]]
        st.markdown("**Missing points**"); [st.warning(x) for x in e["missing_points"]]
    with c2:
        st.markdown("**Weaknesses**"); [st.error(x) for x in e["weaknesses"]]
        st.markdown("**Recommendations**"); [st.info(x) for x in e["recommendations"]]
    for c in e["claims_to_verify"]: st.warning(f"Not supported by your resume, so only claim this if it is true: {c}")
    if e["suggested_structure"]: st.markdown(f"**Suggested structure:** {e['suggested_structure']}")
    if st.button("View example answer"): st.session_state[f"ex{iv['id']}{pos}"] = True
    if st.session_state.get(f"ex{iv['id']}{pos}"):
        st.markdown(e["improved_example"] or "_No example provided._")
        st.caption("Example only. Replace placeholders with your real details; don't copy claims you can't back up.")
n1, n2, n3 = st.columns(3)
if pos > 0 and n1.button("← Previous"): q["answer"] = ans; iv["pos"] -= 1; st.rerun()
if pos < len(items) - 1 and n2.button("Next →"):
    q["answer"] = ans; db(repo.save_answer, sid, iv["id"], pos, ans, q["evaluation"]); iv["pos"] += 1; st.rerun()
if n3.button("🏁 Finish & see report"):
    q["answer"] = ans; db(repo.save_answer, sid, iv["id"], pos, ans, q["evaluation"]); db(repo.complete_interview, sid, iv["id"])
    iv["done"] = True; st.rerun()
with st.expander("Review previous answers"):
    for n, i in enumerate(items[:pos]): st.markdown(f"**Q{n+1}.** {i['question']}"); st.write(i["answer"] or "_not answered_")

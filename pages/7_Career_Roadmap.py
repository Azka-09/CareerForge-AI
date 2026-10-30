import streamlit as st
import ui
from database import repository as repo
from models.resume_models import JobRequirements
from services import career_roadmap_service as rm
from services.llm_service import structured, doc

ui.init_session(); ui.inject_css()
ui.hero("Career Roadmap", "A personalised learning plan from your resume and target job. Progress is saved.")
if not ui.need_resume(): st.stop()
sid = st.session_state.session_id

try:
    if "roadmap" not in st.session_state and (saved := repo.latest_roadmap(sid)):
        st.session_state.roadmap = {"id": saved[0], "title": saved[1], "data": saved[2]}
except Exception:
    st.error("Could not read saved roadmaps. Check database settings.")

with st.expander("Create a new roadmap", expanded="roadmap" not in st.session_state):
    title = st.text_input("Target position")
    jd = st.text_area("Job description", st.session_state.get("job_text", ""), height=150)
    goals = st.text_area("Career goals (optional)", height=70)
    st.session_state.job_text = jd
    if st.button("Generate roadmap", type="primary"):
        if not title.strip() or len(jd.strip()) < 40: st.error("Enter a target position and a fuller job description.")
        else:
            data = ui.ensure_structured()
            if data is not None:
                req = ui.ai_call("Reading job description...", structured, "Extract job requirements. Only include what the text states.",
                                 doc("job_description", jd), JobRequirements, ui.session_cache())
                if req is not None:
                    gaps = rm.build_gap_rows(data.model_dump(), st.session_state.resume.text, req.model_dump(), ui.get_embedder())
                    road = ui.ai_call("Building your roadmap...", rm.generate, data.model_dump_json(), jd, title, goals, gaps, ui.session_cache())
                    if road is not None:
                        d = road.model_dump()
                        try:
                            st.session_state.roadmap = {"id": repo.save_roadmap(sid, title, d), "title": title, "data": d, "gaps": gaps}
                            st.rerun()
                        except Exception: st.error("The roadmap was generated but could not be saved.")

R = st.session_state.get("roadmap")
if not R:
    st.info("Generate a roadmap to see your learning plan."); st.stop()
road, rid = R["data"], R["id"]
tasks = rm.task_list(road)
try: done = repo.done_tasks(sid, rid)
except Exception: st.error("Could not read saved progress."); done = set()
prog = rm.progress(tasks, done)

st.subheader(f"Roadmap: {R['title']}")
m1, m2 = st.columns([1, 2]); m1.metric("Overall progress", f"{prog['pct']}%", f"{prog['done']} of {prog['total']} tasks")
m1.progress(prog["pct"] / 100)
if prog["by_group"]:
    g = prog["by_group"]
    m2.plotly_chart(ui.bar(list(g), [v["done"] / v["total"] for v in g.values()], "Completion by stage"), use_container_width=True)
st.warning("Only add a skill to your resume once you can genuinely demonstrate it. Durations below are rough estimates.")
if road["strengths"]:
    with st.expander("Your existing strengths", expanded=True):
        for s in road["strengths"]: st.success(s)
with st.expander("Skill details"):
    for s in road["skills"]:
        st.markdown(f"**{s['skill']}** · {rm.GROUPS[s['horizon']]}" + (f" · ⏱ ~{s['estimated_duration']} (estimate)" if s["estimated_duration"] else ""))
        if s["why"]: st.write(s["why"])

groups = list(dict.fromkeys(t["group"] for t in tasks))
for gname in groups:
    gp = prog["by_group"][gname]
    with st.expander(f"{gname}  ({gp['done']}/{gp['total']})"):
        for t in (x for x in tasks if x["group"] == gname):
            was = t["key"] in done
            now = st.checkbox(t["label"], value=was, key=f"rm_{rid}_{t['key']}")
            if now != was:
                try: repo.set_task(sid, rid, t["key"], now); st.rerun()
                except Exception: st.error("Could not save progress.")
if st.button("Delete saved roadmaps"):
    repo.delete_roadmaps(sid); st.session_state.pop("roadmap", None); st.rerun()

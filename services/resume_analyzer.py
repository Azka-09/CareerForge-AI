from models.resume_models import ResumeData, AnalysisReport
from services.llm_service import structured, doc

EXTRACT = ("Extract resume information into the schema. Copy facts only from the resume. "
           "Leave fields empty when absent. Keep bullets verbatim.")
ANALYZE = ("You are a resume reviewer. Evaluate: professional summary quality, experience and project "
           "descriptions (achievement orientation, clarity), technical skills, grammar, section completeness"
           "{target}. Return findings with kind strength/weakness, a priority (high/medium/low), and a concrete "
           "suggestion that does NOT require inventing facts. List missing_sections by name.")


def extract_structured(text: str, cache=None) -> ResumeData:
    return structured(EXTRACT, doc("resume", text), ResumeData, cache)


def analyze_resume(data: ResumeData, job_description: str = "", cache=None) -> AnalysisReport:
    target = ", and relevance to the target job description" if job_description.strip() else ""
    user = doc("resume_json", data.model_dump_json())
    if job_description.strip():
        user += "\n" + doc("job_description", job_description)
    report = structured(ANALYZE.format(target=target), user, AnalysisReport, cache)
    order = {"high": 0, "medium": 1, "low": 2}
    report.findings.sort(key=lambda f: order[f.priority])
    return report

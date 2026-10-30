from typing import Literal
from pydantic import BaseModel, Field


class SkillPlan(BaseModel):
    skill: str
    horizon: Literal["short", "medium", "advanced"] = "medium"
    why: str = ""
    topics: list[str] = Field(default_factory=list)
    exercise: str = ""
    project: str = ""
    estimated_duration: str = ""   # always an estimate


class Roadmap(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    skills: list[SkillPlan] = Field(default_factory=list)
    practical_projects: list[str] = Field(default_factory=list)
    portfolio_improvements: list[str] = Field(default_factory=list)
    interview_prep: list[str] = Field(default_factory=list)

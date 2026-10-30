from typing import Literal
from pydantic import BaseModel, Field

Category = Literal["technical", "behavioral", "project", "hr"]


class InterviewQuestion(BaseModel):
    question: str
    category: Category = "technical"
    focus: str = ""


class QuestionSet(BaseModel):
    questions: list[InterviewQuestion]


class Evaluation(BaseModel):
    score: int = Field(ge=0, le=10)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    suggested_structure: str = ""
    improved_example: str = ""
    claims_to_verify: list[str] = Field(default_factory=list)  # claims not supported by the resume

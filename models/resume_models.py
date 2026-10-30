"""Pydantic models. Every field has a default so missing resume info stays empty (never invented)."""
from typing import Literal
from pydantic import BaseModel, Field

Priority = Literal["high", "medium", "low"]


class PersonalInfo(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = Field(default_factory=list)


class Experience(BaseModel):
    title: str = ""
    company: str = ""
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)


class Education(BaseModel):
    degree: str = ""
    institution: str = ""
    dates: str = ""


class ResumeData(BaseModel):
    personal: PersonalInfo = Field(default_factory=PersonalInfo)
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    area: str
    kind: Literal["strength", "weakness"]
    text: str
    suggestion: str = ""
    priority: Priority = "medium"


class AnalysisReport(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)


class Rewrite(BaseModel):
    improved: str
    needs_info: list[str] = Field(default_factory=list)  # questions for the user instead of invented facts


class JobRequirements(BaseModel):
    title: str = ""
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_requirements: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

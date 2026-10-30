from pydantic import BaseModel, Field


class RAGAnswer(BaseModel):
    answer: str
    sufficient: bool = True                      # False when the excerpts do not answer the question
    used_sources: list[int] = Field(default_factory=list)  # 1-based excerpt numbers actually relied on

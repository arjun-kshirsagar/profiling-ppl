import enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EvaluationStatusEnum(str, enum.Enum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class JobInput(BaseModel):
    input_data: dict[str, Any] = Field(
        ..., description="Context variables like linkedin_url or name."
    )
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")


class JobResponse(BaseModel):
    evaluation_id: int
    status: EvaluationStatusEnum
    estimated_time_seconds: int = 45


class EvaluationStatusResponse(BaseModel):
    evaluation_id: int
    status: str
    stage: Optional[str] = None
    summary: Optional[str] = None
    progress: dict[str, str] = Field(default_factory=dict)


class PersonData(BaseModel):
    name: str = Field(..., description="The name of the evaluated person.")
    company: Optional[str] = Field(
        None, description="The current company of the evaluated person."
    )


class PersonaData(BaseModel):
    name: str = Field(description="The name identified for this persona.")
    company: Optional[str] = Field(
        None, description="The current or main company associated with this persona."
    )
    role: Optional[str] = Field(
        None, description="The role or designation of this persona."
    )
    location: Optional[str] = Field(
        None, description="The location associated with this persona."
    )
    description: str = Field(
        description="A brief description of this persona to help the user distinguish them."
    )
    associated_urls: list[str] = Field(
        description="List of URLs that likely belong to this specific persona."
    )


class AgentMemoryItem(BaseModel):
    role: str
    content: Optional[Any] = None
    thought: Optional[str] = None
    action: Optional[str] = None
    tool: Optional[str] = None
    inputs: Optional[dict[str, Any]] = None
    result: Optional[Any] = None


class FinalSourceData(BaseModel):
    url: str = Field(..., description="The URL of the source profile or article.")
    type: str = Field(
        ...,
        description="The type of the source (e.g., 'linkedin', 'github', 'news_article').",
    )
    confidence: float = Field(
        ...,
        description="The confidence score (0.0 to 1.0) of this source belonging to the person.",
    )
    extracted_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured signals extracted from this source.",
    )


class ComprehensiveProfileResponse(BaseModel):
    person: PersonData
    sources: list[FinalSourceData] = Field(default_factory=list)
    summary: str = Field(..., description="The final synthesized professional summary.")
    total_sources: int = Field(
        0, description="The total number of valid sources aggregated."
    )
    found_personas: list[PersonaData] = Field(
        default_factory=list,
        description="List of distinct personas discovered during research (used for disambiguation).",
    )
    follow_up_questions: list[str] = Field(
        default_factory=list,
        description="Questions generated when identity confidence is low to help disambiguate.",
    )
    agent_memory: list[dict] = Field(
        default_factory=list,
        description="The detailed execution trace from the agentic loop.",
    )

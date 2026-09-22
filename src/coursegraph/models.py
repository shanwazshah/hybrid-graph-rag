from typing import Any

from pydantic import BaseModel, Field


class Source(BaseModel):
    id: str
    title: str
    url: str
    excerpt: str
    course_code: str


class Course(BaseModel):
    code: str
    title: str
    department: str
    level: int
    credits: int
    description: str
    topics: list[str]
    source_id: str


class GraphPath(BaseModel):
    nodes: list[str]
    relationships: list[str] = Field(default_factory=list)
    description: str = ""


class Citation(BaseModel):
    source_id: str
    title: str
    url: str
    excerpt: str
    supports: list[str] = Field(default_factory=list)


class ToolTrace(BaseModel):
    tool: str
    status: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class AgentResponse(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    graph_paths: list[GraphPath]
    evidence_course_codes: list[str]
    verified: bool
    verification_issues: list[str] = Field(default_factory=list)
    tool_trace: list[ToolTrace]
    latency_ms: float


class GraphQueryRequest(BaseModel):
    query_id: str
    params: dict[str, Any] = Field(default_factory=dict)


class GraphQueryResponse(BaseModel):
    query_id: str
    records: list[dict[str, Any]]
    citations: list[Citation]
    graph_paths: list[GraphPath]


class DegreePlanRequest(BaseModel):
    program_code: str = "BSCS-AI"
    completed_courses: list[str] = Field(default_factory=list)
    max_credits_per_term: int = Field(default=15, ge=3, le=21)
    start_term: str = Field(default="Fall", pattern="^(?i:fall|spring)$")
    max_terms: int = Field(default=8, ge=1, le=12)


class PlannedCourse(BaseModel):
    code: str
    title: str
    credits: int
    offered_terms: list[str]


class PlannedSemester(BaseModel):
    term_number: int
    term: str
    label: str
    credits: int
    courses: list[PlannedCourse]


class DegreePlanResponse(BaseModel):
    program_code: str
    program_title: str
    start_term: str
    max_credits_per_term: int
    completed: list[str]
    semesters: list[PlannedSemester]
    feasible: bool
    unscheduled: list[str]
    planned_credits: int
    solver: str = "csp_exact"
    constraints: list[str]
    citations: list[Citation]
    graph_paths: list[GraphPath]


class ImpactRequest(BaseModel):
    course_code: str
    program_code: str = "BSCS-AI"


class ImpactResponse(BaseModel):
    course: str
    program_code: str
    affected_courses: list[str]
    affected_count: int
    citations: list[Citation]
    graph_paths: list[GraphPath]

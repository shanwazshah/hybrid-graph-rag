from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from coursegraph.agent import CourseGraphAgent
from coursegraph.config import get_settings
from coursegraph.models import (
    AgentRequest,
    AgentResponse,
    Course,
    DegreePlanRequest,
    DegreePlanResponse,
    GraphQueryRequest,
    GraphQueryResponse,
    ImpactRequest,
    ImpactResponse,
    Source,
)
from coursegraph.planning import DegreePlanner
from coursegraph.repository import GraphRepository, InMemoryGraphRepository, Neo4jGraphRepository


def _configured_repository() -> GraphRepository:
    settings = get_settings()
    if settings.coursegraph_backend == "memory":
        return InMemoryGraphRepository()
    return Neo4jGraphRepository(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)


def create_app(repository: GraphRepository | None = None) -> FastAPI:
    managed_repository = repository is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repo = repository or _configured_repository()
        app.state.repository = repo
        app.state.agent = CourseGraphAgent(repo)
        if isinstance(repo, Neo4jGraphRepository):
            repo.ensure_schema()
        yield
        if managed_repository:
            repo.close()

    application = FastAPI(
        title="CourseGraph Agent API",
        version="0.1.0",
        description="Vectorless graph RAG over a university course catalog.",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8501"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    def repo_from(request: Request) -> GraphRepository:
        return request.app.state.repository

    def agent_from(request: Request) -> CourseGraphAgent:
        return request.app.state.agent

    @application.get("/health", tags=["operations"])
    def health(repo: GraphRepository = Depends(repo_from)) -> dict[str, Any]:
        try:
            healthy = repo.health()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Graph backend unavailable: {type(exc).__name__}") from exc
        return {"status": "ok" if healthy else "degraded", "graph": type(repo).__name__, "vectorless": True}

    @application.get("/courses/search", response_model=list[Course], tags=["catalog"])
    def search_courses(
        q: str = Query(min_length=1, max_length=200),
        department: str | None = None,
        level: int | None = Query(default=None, ge=100, le=900),
        limit: int = Query(default=8, ge=1, le=50),
        repo: GraphRepository = Depends(repo_from),
    ) -> list[Course]:
        return repo.search_courses(q, department=department, level=level, limit=limit)

    @application.get("/courses/{code}", response_model=Course, tags=["catalog"])
    def get_course(code: str, repo: GraphRepository = Depends(repo_from)) -> Course:
        course = repo.get_course(code)
        if not course:
            raise HTTPException(status_code=404, detail=f"Course not found: {code.upper()}")
        return course

    @application.get("/sources/{source_id}", response_model=Source, tags=["provenance"])
    def get_source(source_id: str, repo: GraphRepository = Depends(repo_from)) -> Source:
        source = repo.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
        return source

    @application.post("/graph/query", response_model=GraphQueryResponse, tags=["graph"])
    def graph_query(payload: GraphQueryRequest, repo: GraphRepository = Depends(repo_from)) -> GraphQueryResponse:
        try:
            result = repo.graph_query(payload.query_id, payload.params)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return GraphQueryResponse(
            query_id=payload.query_id,
            records=result["records"],
            citations=result["citations"],
            graph_paths=result["graph_paths"],
        )

    @application.post("/agent/query", response_model=AgentResponse, tags=["agent"])
    def ask_agent(payload: AgentRequest, agent: CourseGraphAgent = Depends(agent_from)) -> AgentResponse:
        try:
            return agent.ask(payload.question)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.post("/planning/degree", response_model=DegreePlanResponse, tags=["planning"])
    def build_degree_plan(
        payload: DegreePlanRequest, repo: GraphRepository = Depends(repo_from)
    ) -> DegreePlanResponse:
        try:
            result = DegreePlanner(repo).plan(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return DegreePlanResponse(**result)

    @application.post("/planning/impact", response_model=ImpactResponse, tags=["planning"])
    def analyze_impact(
        payload: ImpactRequest, repo: GraphRepository = Depends(repo_from)
    ) -> ImpactResponse:
        try:
            result = DegreePlanner(repo).impact(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ImpactResponse(**result)

    return application


app = create_app()

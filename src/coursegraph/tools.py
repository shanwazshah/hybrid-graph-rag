from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from coursegraph.models import Citation, GraphPath
from coursegraph.planning import DegreePlanner
from coursegraph.repository import GraphRepository


def build_tools(repository: GraphRepository) -> list[StructuredTool]:
    """Create the eight tools available to the single CourseGraph agent."""

    planner = DegreePlanner(repository)

    def course_search(query: str, department: str | None = None, level: int | None = None, limit: int = 8) -> dict[str, Any]:
        """Search catalog text without vectors; optionally filter by department and exact course level."""
        found = repository.search_courses(query, department=department, level=level, limit=limit)
        codes = [course.code for course in found]
        citations = repository.citations_for(codes)
        paths = [GraphPath(nodes=[code], description="Full-text search result node") for code in codes]
        if not found:
            overview = repository.get_source("catalog:overview")
            if overview:
                citations = [
                    Citation(
                        source_id=overview.id, title=overview.title, url=overview.url,
                        excerpt=overview.excerpt, supports=["CATALOG"],
                    )
                ]
                codes = ["CATALOG"]
                paths = [GraphPath(nodes=["CATALOG", "catalog:overview"], relationships=["HAS_SOURCE"], description="Catalog search provenance")]
        return {
            "kind": "course_search",
            "query": query,
            "courses": [course.model_dump() for course in found],
            "evidence_course_codes": codes,
            "citations": [citation.model_dump() for citation in citations],
            "graph_paths": [path.model_dump() for path in paths],
        }

    def prerequisite_check(course_code: str, completed_courses: list[str] | None = None) -> dict[str, Any]:
        """Check whether completed courses satisfy all direct and transitive prerequisites."""
        return repository.check_prerequisites(course_code, completed_courses or [])

    def learning_path(goal_course: str, completed_courses: list[str] | None = None) -> dict[str, Any]:
        """Return a prerequisite-respecting course order for reaching a target course."""
        return repository.learning_path(goal_course, completed_courses or [])

    def graph_query(query_id: str, params: dict[str, Any]) -> dict[str, Any]:
        """Run one named, allowlisted, read-only graph query. Raw Cypher is never accepted."""
        return repository.graph_query(query_id, params)

    def source_retrieval(course_codes: list[str]) -> dict[str, Any]:
        """Retrieve authoritative catalog source records for course codes."""
        normalised = list(dict.fromkeys(code.upper().strip() for code in course_codes))
        citations = repository.citations_for(normalised)
        existing = [item.supports[0] for item in citations if item.supports]
        return {
            "kind": "source_retrieval",
            "evidence_course_codes": existing,
            "citations": [item.model_dump() for item in citations],
            "graph_paths": [
                GraphPath(nodes=[code, f"catalog:{code}"], relationships=["HAS_SOURCE"], description="Catalog provenance").model_dump()
                for code in existing
            ],
        }

    def degree_plan(
        program_code: str = "BSCS-AI",
        completed_courses: list[str] | None = None,
        max_credits_per_term: int = 15,
        start_term: str = "Fall",
        max_terms: int = 8,
    ) -> dict[str, Any]:
        """Build a feasible term-by-term program plan using prerequisites, offerings, and a credit cap."""
        return planner.plan(
            program_code=program_code,
            completed_courses=completed_courses or [],
            max_credits_per_term=max_credits_per_term,
            start_term=start_term,
            max_terms=max_terms,
        )

    def impact_analysis(course_code: str, program_code: str = "BSCS-AI") -> dict[str, Any]:
        """Show which downstream program requirements are affected if a course is delayed or failed."""
        return planner.impact(course_code=course_code, program_code=program_code)

    def answer_verification(answer: str, citations: list[dict[str, Any]], graph_paths: list[dict[str, Any]]) -> dict[str, Any]:
        """Verify that cited sources exist, appear in the answer, and accompany graph evidence."""
        issues: list[str] = []
        if not citations:
            issues.append("No supporting catalog citations were returned.")
        if not graph_paths or not any(path.get("nodes") for path in graph_paths):
            issues.append("No supporting graph path was returned.")
        for citation in citations:
            source_id = str(citation.get("source_id", ""))
            if not source_id or repository.get_source(source_id) is None:
                issues.append(f"Unknown source: {source_id or '<missing>'}")
            elif f"[{source_id}]" not in answer:
                issues.append(f"Citation marker missing from answer: {source_id}")
        for path in graph_paths:
            nodes = path.get("nodes", [])
            relationships = path.get("relationships", [])
            if nodes and len(relationships) not in {0, len(nodes) - 1}:
                issues.append(f"Malformed graph path: {nodes}")
        return {"verified": not issues, "issues": issues}

    specs = [
        (course_search, "course_search"),
        (prerequisite_check, "prerequisite_check"),
        (learning_path, "learning_path"),
        (graph_query, "graph_query"),
        (source_retrieval, "source_retrieval"),
        (degree_plan, "degree_plan"),
        (impact_analysis, "impact_analysis"),
        (answer_verification, "answer_verification"),
    ]
    return [StructuredTool.from_function(func=func, name=name, description=func.__doc__ or name) for func, name in specs]

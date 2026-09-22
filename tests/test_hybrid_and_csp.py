import pytest

from coursegraph.agent import CourseGraphAgent
from coursegraph.config import Settings
from coursegraph.planning import DegreePlanner
from coursegraph.repository import InMemoryGraphRepository


@pytest.fixture
def repository() -> InMemoryGraphRepository:
    return InMemoryGraphRepository()


@pytest.fixture
def planner(repository: InMemoryGraphRepository) -> DegreePlanner:
    return DegreePlanner(repository)


def test_csp_solver_finds_exact_feasible_plan(planner: DegreePlanner) -> None:
    plan = planner.plan(max_credits_per_term=15, max_terms=8)
    assert plan["feasible"] is True
    assert plan["solver"] == "csp_exact"
    assert plan["planned_credits"] == 84
    assert len(plan["semesters"]) == 8


def test_csp_solver_falls_back_to_greedy_when_infeasible(planner: DegreePlanner) -> None:
    plan = planner.plan(max_credits_per_term=15, max_terms=2)
    assert plan["feasible"] is False
    assert plan["solver"] == "heuristic_greedy"
    assert len(plan["unscheduled"]) > 0


def test_hybrid_rrf_search_ranks_relevant_courses(repository: InMemoryGraphRepository) -> None:
    results = repository.search_courses("knowledge graphs and automated reasoning", limit=5)
    assert len(results) > 0
    assert results[0].code == "AI202"

    robot_results = repository.search_courses("robot motion planning and control", limit=5)
    assert any(c.code == "AI230" for c in robot_results)


def test_dual_mode_agent_offline_initialization(repository: InMemoryGraphRepository) -> None:
    settings = Settings(llm_provider="none")
    agent = CourseGraphAgent(repository, settings=settings)
    assert agent.llm is None
    response = agent.ask("What is the learning path to AI302?")
    assert response.verified is True
    assert "AI302" in response.evidence_course_codes
    assert len(response.citations) > 0

import pytest

from coursegraph.agent import CourseGraphAgent
from coursegraph.repository import InMemoryGraphRepository


@pytest.fixture(scope="module")
def agent() -> CourseGraphAgent:
    return CourseGraphAgent(InMemoryGraphRepository())


@pytest.mark.parametrize(
    ("question", "expected_tool", "expected_code"),
    [
        ("Find courses about graph machine learning", "course_search", "AI310"),
        ("Can I take CS102 if I completed CS101?", "prerequisite_check", "CS102"),
        ("What is the learning path to AI302?", "learning_path", "AI302"),
        ("What connects MATH210 and AI310?", "graph_query", "MATH210"),
        ("Show the source for CS320", "source_retrieval", "CS320"),
        ("Create an 8-semester degree plan with 15 credits per term", "degree_plan", "CS410"),
        ("What if I delay CS201?", "impact_analysis", "AI302"),
    ],
)
def test_agent_routes_calls_and_verifies(agent: CourseGraphAgent, question: str, expected_tool: str, expected_code: str) -> None:
    response = agent.ask(question)
    assert response.tool_trace[0].tool == expected_tool
    assert response.tool_trace[-1].tool == "answer_verification"
    assert response.verified is True
    assert expected_code in response.evidence_course_codes
    assert response.citations
    assert response.graph_paths
    assert all(f"[{citation.source_id}]" in response.answer for citation in response.citations)


def test_agent_reports_missing_prerequisites(agent: CourseGraphAgent) -> None:
    response = agent.ask("Can I take AI302 if I completed AI201?")
    assert "Not yet" in response.answer
    assert "AI210" in response.answer
    assert "AI301" in response.answer


def test_no_match_answer_still_has_provenance(agent: CourseGraphAgent) -> None:
    response = agent.ask("Find a course about underwater basket weaving on Mars")
    assert "No matching" in response.answer
    assert response.verified is True
    assert response.citations[0].source_id == "catalog:overview"
    assert response.graph_paths[0].relationships == ["HAS_SOURCE"]


def test_invalid_course_answer_still_has_provenance(agent: CourseGraphAgent) -> None:
    response = agent.ask("Can I take XYZ999?")
    assert "could not complete" in response.answer
    assert response.verified is True
    assert response.citations[0].source_id == "catalog:overview"
    assert response.graph_paths


def test_degree_plan_answer_explains_constraints(agent: CourseGraphAgent) -> None:
    response = agent.ask("Create an 8-semester degree plan with 15 credits per term")
    assert "feasible" in response.answer
    assert "Fall" in response.answer and "Spring" in response.answer
    assert "No term exceeds 15 credits" in response.answer
    assert response.verified is True

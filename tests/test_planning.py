import pytest

from coursegraph.catalog import prerequisite_map
from coursegraph.planning import DegreePlanner
from coursegraph.programs import offering_terms
from coursegraph.repository import InMemoryGraphRepository


@pytest.fixture
def planner() -> DegreePlanner:
    return DegreePlanner(InMemoryGraphRepository())


def test_degree_plan_respects_all_constraints(planner: DegreePlanner) -> None:
    result = planner.plan(max_credits_per_term=15, max_terms=8)
    assert result["feasible"] is True
    assert result["planned_credits"] == 84
    assert len(result["semesters"]) == 8
    completed: set[str] = set()
    prerequisites = prerequisite_map()
    for semester in result["semesters"]:
        assert semester["credits"] <= 15
        for course in semester["courses"]:
            assert set(prerequisites[course["code"]]).issubset(completed)
            assert semester["term"] in offering_terms(course["code"])
        completed.update(course["code"] for course in semester["courses"])


def test_completed_courses_are_not_rescheduled(planner: DegreePlanner) -> None:
    result = planner.plan(completed_courses=["CS101", "MATH101"])
    scheduled = {course["code"] for semester in result["semesters"] for course in semester["courses"]}
    assert "CS101" not in scheduled
    assert "MATH101" not in scheduled
    assert result["planned_credits"] == 78


def test_short_term_limit_is_reported_as_infeasible(planner: DegreePlanner) -> None:
    result = planner.plan(max_terms=2)
    assert result["feasible"] is False
    assert result["unscheduled"]


def test_impact_analysis_follows_transitive_graph_paths(planner: DegreePlanner) -> None:
    result = planner.impact("CS201")
    assert {"AI101", "AI201", "AI302", "CS320"}.issubset(result["affected_courses"])
    assert result["affected_count"] == 8
    assert all(path["nodes"][0] == "CS201" for path in result["graph_paths"])


def test_planner_validates_constraints(planner: DegreePlanner) -> None:
    with pytest.raises(ValueError, match="between 3 and 21"):
        planner.plan(max_credits_per_term=30)
    with pytest.raises(ValueError, match="Unknown completed"):
        planner.plan(completed_courses=["FAKE999"])


import pytest

from coursegraph.repository import InMemoryGraphRepository


@pytest.fixture
def repository() -> InMemoryGraphRepository:
    return InMemoryGraphRepository()


def test_full_text_search_finds_topic(repository: InMemoryGraphRepository) -> None:
    results = repository.search_courses("knowledge graphs and reasoning")
    assert results[0].code == "AI202"


def test_prerequisite_check_handles_completed_courses(repository: InMemoryGraphRepository) -> None:
    result = repository.check_prerequisites("AI302", ["AI301", "AI210"])
    assert result["eligible"] is True
    assert result["missing"] == []
    assert any(path["nodes"][:2] == ["AI302", "AI301"] for path in result["graph_paths"])


def test_prerequisite_check_reports_transitive_gaps(repository: InMemoryGraphRepository) -> None:
    result = repository.check_prerequisites("AI302", [])
    assert result["eligible"] is False
    assert {"AI301", "AI210", "AI201", "AI101"}.issubset(result["missing"])


def test_learning_path_is_topological(repository: InMemoryGraphRepository) -> None:
    result = repository.learning_path("AI302", [])
    order = result["recommended_order"]
    assert order[-1] == "AI302"
    assert order.index("AI201") < order.index("AI301") < order.index("AI302")
    assert order.index("CS320") < order.index("AI210") < order.index("AI302")


def test_shortest_path_is_graph_backed(repository: InMemoryGraphRepository) -> None:
    result = repository.graph_query("shortest_path", {"from_code": "MATH210", "to_code": "AI310"})
    assert result["records"][0]["path"] == ["MATH210", "MATH310", "AI310"]


def test_unknown_query_is_rejected(repository: InMemoryGraphRepository) -> None:
    with pytest.raises(ValueError, match="Unknown query_id"):
        repository.graph_query("MATCH (n) DETACH DELETE n", {})


def test_extra_parameters_are_rejected(repository: InMemoryGraphRepository) -> None:
    with pytest.raises(ValueError, match="Unexpected parameters"):
        repository.graph_query("course_details", {"code": "CS101", "cypher": "DELETE n"})


def test_program_requirements_are_graph_backed(repository: InMemoryGraphRepository) -> None:
    result = repository.graph_query("program_requirements", {"program_code": "BSCS-AI"})
    assert len(result["records"]) == 28
    assert {"AI302", "CS410"}.issubset(result["evidence_course_codes"])
    assert all(path["relationships"] == ["REQUIRES_COURSE"] for path in result["graph_paths"])

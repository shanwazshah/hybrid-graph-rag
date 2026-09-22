import os

import pytest

from coursegraph.config import Settings
from coursegraph.planning import DegreePlanner
from coursegraph.repository import Neo4jGraphRepository


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def repository() -> Neo4jGraphRepository:
    if os.getenv("RUN_NEO4J_TESTS") != "1":
        pytest.skip("Set RUN_NEO4J_TESTS=1 to run against Docker Compose Neo4j")
    settings = Settings()
    repo = Neo4jGraphRepository(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    repo.seed_catalog()
    yield repo
    repo.close()


def test_fulltext_index_and_graph_traversal(repository: Neo4jGraphRepository) -> None:
    assert repository.search_courses("knowledge graphs")[0].code == "AI202"
    path = repository.learning_path("AI302", [])
    assert path["recommended_order"][-1] == "AI302"
    assert path["graph_paths"]


def test_allowlisted_query(repository: Neo4jGraphRepository) -> None:
    result = repository.graph_query("shortest_path", {"from_code": "MATH210", "to_code": "AI310"})
    assert result["records"][0]["path"] == ["MATH210", "MATH310", "AI310"]


def test_program_graph_and_degree_planner(repository: Neo4jGraphRepository) -> None:
    requirements = repository.graph_query("program_requirements", {"program_code": "BSCS-AI"})
    assert len(requirements["records"]) == 28
    plan = DegreePlanner(repository).plan(max_credits_per_term=15, max_terms=8)
    assert plan["feasible"] is True
    assert plan["planned_credits"] == 84

from fastapi.testclient import TestClient

from coursegraph.api import create_app
from coursegraph.repository import InMemoryGraphRepository


def test_health_and_search_endpoints() -> None:
    app = create_app(InMemoryGraphRepository())
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["vectorless"] is True
        search = client.get("/courses/search", params={"q": "distributed consensus"})
        assert search.status_code == 200
        assert search.json()[0]["code"] == "CS303"


def test_agent_endpoint_returns_citations_and_paths() -> None:
    app = create_app(InMemoryGraphRepository())
    with TestClient(app) as client:
        response = client.post("/agent/query", json={"question": "What is the learning path to HCI301?"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["verified"] is True
        assert payload["citations"]
        assert payload["graph_paths"]


def test_graph_endpoint_rejects_raw_cypher() -> None:
    app = create_app(InMemoryGraphRepository())
    with TestClient(app) as client:
        response = client.post("/graph/query", json={"query_id": "MATCH (n) RETURN n", "params": {}})
        assert response.status_code == 400


def test_planning_endpoints_return_feasible_plan_and_impact() -> None:
    app = create_app(InMemoryGraphRepository())
    with TestClient(app) as client:
        plan = client.post(
            "/planning/degree",
            json={"program_code": "BSCS-AI", "max_credits_per_term": 15, "max_terms": 8},
        )
        assert plan.status_code == 200
        assert plan.json()["feasible"] is True
        assert len(plan.json()["semesters"]) == 8
        impact = client.post(
            "/planning/impact",
            json={"course_code": "CS201", "program_code": "BSCS-AI"},
        )
        assert impact.status_code == 200
        assert "AI302" in impact.json()["affected_courses"]

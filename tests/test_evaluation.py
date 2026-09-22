import json
from pathlib import Path

from coursegraph.evaluation import evaluate
from coursegraph.repository import InMemoryGraphRepository


DATASET = Path(__file__).parents[1] / "evals" / "questions.json"


def test_evaluation_set_has_at_least_thirty_questions() -> None:
    cases = json.loads(DATASET.read_text(encoding="utf-8"))
    assert len(cases) >= 40
    assert len({case["id"] for case in cases}) == len(cases)


def test_evaluation_smoke_metrics() -> None:
    report = evaluate(InMemoryGraphRepository(), DATASET)
    assert report["metrics"]["question_count"] >= 40
    assert report["metrics"]["answer_accuracy"] >= 0.90
    assert report["metrics"]["citation_correctness"] == 1.0
    assert report["metrics"]["tool_success_rate"] == 1.0

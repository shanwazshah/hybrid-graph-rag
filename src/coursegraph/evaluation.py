from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from coursegraph.agent import CourseGraphAgent
from coursegraph.config import get_settings
from coursegraph.repository import GraphRepository, InMemoryGraphRepository, Neo4jGraphRepository


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * percentile), len(ordered) - 1)
    return ordered[index]


def evaluate(repository: GraphRepository, dataset_path: Path) -> dict[str, Any]:
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))
    agent = CourseGraphAgent(repository)
    results = []
    for case in cases:
        response = agent.ask(case["question"])
        expected = set(case.get("expected_codes", []))
        evidence = set(response.evidence_course_codes)
        accuracy = expected.issubset(evidence)
        citations_valid = bool(response.citations) and all(
            repository.get_source(item.source_id) is not None
            and set(item.supports).issubset(evidence)
            and f"[{item.source_id}]" in response.answer
            for item in response.citations
        )
        tool_success = bool(response.tool_trace) and all(item.status == "success" for item in response.tool_trace)
        # RAG Triad: Grounded Faithfulness (no unevidenced course hallucination) & Context Recall
        raw_mentioned = re.findall(r"\b[A-Z]{2,5}\s?-?\d{3}\b", response.answer)
        mentioned_codes = {c.replace(" ", "").replace("-", "").upper() for c in raw_mentioned}
        allowed_evidence = evidence | {"CATALOG", "BSCS", "AI", "BSCS-AI"}
        for cit in response.citations:
            allowed_evidence.update(cit.supports)
            for c in re.findall(r"\b[A-Z]{2,5}\s?-?\d{3}\b", cit.excerpt):
                allowed_evidence.add(c.replace(" ", "").replace("-", "").upper())

        faithfulness = bool(mentioned_codes.issubset(allowed_evidence)) or len(mentioned_codes) == 0
        context_recall = round(len(expected & evidence) / len(expected), 4) if expected else 1.0

        results.append(
            {
                "id": case["id"],
                "question": case["question"],
                "expected_codes": sorted(expected),
                "evidence_codes": response.evidence_course_codes,
                "accuracy": accuracy,
                "citation_correct": citations_valid,
                "tool_success": tool_success,
                "verified": response.verified,
                "faithfulness": faithfulness,
                "context_recall": context_recall,
                "latency_ms": response.latency_ms,
            }
        )
    count = len(results)
    latencies = [item["latency_ms"] for item in results]
    metrics = {
        "question_count": count,
        "answer_accuracy": round(sum(item["accuracy"] for item in results) / count, 4),
        "citation_correctness": round(sum(item["citation_correct"] for item in results) / count, 4),
        "faithfulness": round(sum(item["faithfulness"] for item in results) / count, 4),
        "context_recall": round(sum(item["context_recall"] for item in results) / count, 4),
        "tool_success_rate": round(sum(item["tool_success"] for item in results) / count, 4),
        "verified_answer_rate": round(sum(item["verified"] for item in results) / count, 4),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 2),
            "p50": round(_percentile(latencies, 0.50), 2),
            "p95": round(_percentile(latencies, 0.95), 2),
        },
    }
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "metrics": metrics, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CourseGraph Agent")
    parser.add_argument("--dataset", type=Path, default=Path("evals/questions.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/evaluation_report.json"))
    parser.add_argument("--backend", choices=["memory", "neo4j"], default="memory")
    parser.add_argument("--fail-under", type=float, default=0.90)
    args = parser.parse_args()

    if args.backend == "neo4j":
        settings = get_settings()
        repository: GraphRepository = Neo4jGraphRepository(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    else:
        repository = InMemoryGraphRepository()
    try:
        report = evaluate(repository, args.dataset)
    finally:
        repository.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["metrics"], indent=2))
    metrics = report["metrics"]
    if min(metrics["answer_accuracy"], metrics["citation_correctness"], metrics["tool_success_rate"]) < args.fail_under:
        sys.exit(1)


if __name__ == "__main__":
    main()


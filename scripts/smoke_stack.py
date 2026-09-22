"""Fail-fast smoke test for a running CourseGraph Compose stack."""

from __future__ import annotations

import os
import sys

import requests


def main() -> None:
    api_url = os.getenv("COURSEGRAPH_API_URL", "http://localhost:8000").rstrip("/")
    ui_url = os.getenv("COURSEGRAPH_UI_URL", "http://localhost:8501").rstrip("/")
    health = requests.get(f"{api_url}/health", timeout=10)
    health.raise_for_status()
    payload = health.json()
    if payload.get("status") != "ok" or payload.get("vectorless") is not True:
        raise RuntimeError(f"Unexpected health response: {payload}")
    answer = requests.post(
        f"{api_url}/agent/query",
        json={"question": "What is the learning path to AI302?"},
        timeout=30,
    )
    answer.raise_for_status()
    result = answer.json()
    if not result.get("verified") or not result.get("citations") or not result.get("graph_paths"):
        raise RuntimeError(f"Agent response was not fully grounded: {result}")
    ui = requests.get(ui_url, timeout=10)
    ui.raise_for_status()
    if "streamlit" not in ui.text.lower():
        raise RuntimeError("Streamlit shell was not returned")
    print(
        f"OK: {payload['graph']} is healthy; agent returned {len(result['citations'])} citations "
        f"and {len(result['graph_paths'])} paths; UI returned HTTP {ui.status_code}."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        raise

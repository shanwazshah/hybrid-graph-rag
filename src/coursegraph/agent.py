from __future__ import annotations

import json
import re
import time
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

import os

from coursegraph.config import Settings, get_settings
from coursegraph.models import AgentResponse, Citation, GraphPath, ToolTrace
from coursegraph.repository import GraphRepository
from coursegraph.tools import build_tools


COURSE_CODE = re.compile(r"\b[A-Z]{2,5}\s?-?\d{3}\b", re.IGNORECASE)


class AgentState(TypedDict, total=False):
    question: str
    messages: Annotated[list[BaseMessage], add_messages]
    phase: str
    selected_tool: str
    selected_arguments: dict[str, Any]
    result: dict[str, Any]
    answer: str
    citations: list[dict[str, Any]]
    graph_paths: list[dict[str, Any]]
    evidence_course_codes: list[str]
    verified: bool
    verification_issues: list[str]
    tool_trace: list[dict[str, Any]]


def _codes(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(0).replace(" ", "").replace("-", "").upper() for match in COURSE_CODE.finditer(text)))


def _last_tool_payload(messages: list[BaseMessage]) -> dict[str, Any]:
    for message in reversed(messages):
        if isinstance(message, ToolMessage):
            content = message.content
            if isinstance(content, dict):
                return content
            try:
                return json.loads(content)
            except (TypeError, json.JSONDecodeError):
                return {"error": str(content)}
    return {"error": "Tool returned no payload"}


def _citation_markers(citations: list[dict[str, Any]]) -> str:
    return " ".join(f"[{item['source_id']}]" for item in citations if item.get("source_id"))


def _format_answer(result: dict[str, Any]) -> str:
    kind = result.get("kind")
    citations = result.get("citations", [])
    markers = _citation_markers(citations)
    if result.get("error"):
        return f"I could not complete the graph lookup: {result['error']}\n\nEvidence: {markers}"
    if kind == "course_search":
        found = result.get("courses", [])
        if not found:
            return f"No matching catalog courses were found. Try a course code or a more specific topic.\n\nEvidence: {markers}"
        lines = [f"I found {len(found)} relevant course{'s' if len(found) != 1 else ''}:"]
        lines.extend(f"- **{item['code']} — {item['title']}** ({item['credits']} credits) [catalog:{item['code']}]" for item in found)
        return "\n".join(lines)
    if kind == "prerequisite_check":
        code = result["course"]
        if result["eligible"]:
            lead = f"Yes. Based on the supplied completed courses, you satisfy the prerequisite graph for **{code}**."
        else:
            lead = f"Not yet. Before **{code}**, the graph shows these missing courses: **{', '.join(result['missing'])}**."
        return f"{lead}\n\nEvidence: {markers}"
    if kind == "learning_path":
        order = " → ".join(result.get("recommended_order", []))
        return f"A prerequisite-respecting path to **{result['goal']}** is:\n\n**{order}**\n\nEvidence: {markers}"
    if kind == "degree_plan":
        status = "feasible" if result["feasible"] else "incomplete within the requested term limit"
        lines = [
            f"A **{status}** constraint-aware plan for **{result['program_title']}** is:",
            "",
        ]
        for semester in result["semesters"]:
            if not semester["courses"]:
                lines.append(f"- **{semester['label']}**: no eligible modeled courses")
                continue
            course_list = ", ".join(
                f"{course['code']} [catalog:{course['code']}]" for course in semester["courses"]
            )
            lines.append(f"- **{semester['label']}** ({semester['credits']} credits): {course_list}")
        if result["unscheduled"]:
            lines.extend(["", f"Unscheduled: **{', '.join(result['unscheduled'])}**"])
        lines.extend(["", f"Constraints: {' '.join(result['constraints'])}", "", f"Evidence: {markers}"])
        return "\n".join(lines)
    if kind == "impact_analysis":
        affected = result.get("affected_courses", [])
        if affected:
            lead = (
                f"Delaying **{result['course']}** affects **{result['affected_count']}** downstream "
                f"requirements in {result['program_code']}: **{', '.join(affected)}**."
            )
        else:
            lead = f"**{result['course']}** has no downstream requirements in {result['program_code']}."
        return f"{lead}\n\nEvidence: {markers}"
    if kind == "source_retrieval":
        if not citations:
            return "No catalog source was found for those course codes."
        lines = ["Catalog sources:"]
        lines.extend(f"- **{item['title']}** — {item['excerpt']} [{item['source_id']}]" for item in citations)
        return "\n".join(lines)
    if kind == "graph_query":
        query_id = result.get("query_id", "graph query")
        records = result.get("records", [])
        if not records:
            return f"The allowlisted **{query_id}** query returned no connected courses."
        if query_id == "shortest_path":
            path = records[0].get("path", [])
            body = " ↔ ".join(path) if path else "No prerequisite connection found"
        elif query_id == "unlocks":
            body = ", ".join(record["code"] for record in records[:12])
        elif query_id == "prerequisites":
            unique = list(dict.fromkeys(node for record in records for node in record.get("path", [])[1:]))
            body = ", ".join(unique) if unique else "No prerequisites"
        elif query_id == "course_details":
            item = records[0]
            body = f"{item['code']} — {item['title']}; prerequisites: {', '.join(item.get('prerequisites', [])) or 'none'}"
        else:
            body = ", ".join(f"{item['code']} — {item['title']}" for item in records[:12])
        return f"**{query_id.replace('_', ' ').title()}**: {body}\n\nEvidence: {markers}"
    return f"The graph lookup completed.\n\nEvidence: {markers}"


class CourseGraphAgent:
    """Dual-mode LangGraph agent combining real LLM tool-calling with deterministic fast-paths."""

    def __init__(self, repository: GraphRepository, settings: Settings | None = None) -> None:
        self.repository = repository
        self.settings = settings or get_settings()
        self.llm = self._build_llm()
        tools = build_tools(repository)
        self._tools = {tool.name: tool for tool in tools}
        self._tool_instances = tools
        self._model_with_tools = self.llm.bind_tools(tools) if self.llm is not None else None
        builder = StateGraph(AgentState)
        builder.add_node("plan", self._plan)
        builder.add_node("tools", ToolNode(tools, handle_tool_errors=True))
        builder.add_node("synthesize", self._synthesize)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "plan")
        builder.add_edge("plan", "tools")
        builder.add_conditional_edges("tools", self._after_tools, {"synthesize": "synthesize", "finalize": "finalize"})
        builder.add_edge("synthesize", "tools")
        builder.add_edge("finalize", END)
        self.graph = builder.compile()

    def _build_llm(self) -> Any:
        provider = self.settings.llm_provider
        if provider == "openai":
            api_key = self.settings.openai_api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                return None
            try:
                from langchain_openai import ChatOpenAI

                return ChatOpenAI(
                    model=self.settings.llm_model,
                    api_key=api_key,
                    base_url=self.settings.openai_base_url,
                    temperature=0,
                )
            except Exception:
                return None
        elif provider == "gemini":
            api_key = self.settings.gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                return None
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI

                return ChatGoogleGenerativeAI(
                    model=self.settings.llm_model,
                    google_api_key=api_key,
                    temperature=0,
                )
            except Exception:
                return None
        return None

    @staticmethod
    def _route(question: str) -> tuple[str, dict[str, Any]]:
        lower = question.lower()
        codes = _codes(question)
        level_match = re.search(r"\b([1-4]00)[ -]?level\b", lower)
        department_match = re.search(r"\b(ai|cs|data|math|hci|infs)\b", lower)

        if any(phrase in lower for phrase in ("what if", "if i fail", "if i drop", "if i delay", "impact of")) and codes:
            return "impact_analysis", {"course_code": codes[0], "program_code": "BSCS-AI"}

        if any(phrase in lower for phrase in ("semester plan", "degree plan", "study plan", "plan my degree", "graduate in")):
            credit_match = re.search(r"\b(\d{1,2})\s*credits?\b", lower)
            term_match = re.search(r"\b(\d{1,2})\s*(?:semesters?|terms?)\b", lower)
            return "degree_plan", {
                "program_code": "BSCS-AI",
                "completed_courses": codes,
                "max_credits_per_term": int(credit_match.group(1)) if credit_match else 15,
                "start_term": "Spring" if re.search(r"(?:start|starting|begin)\s+(?:in\s+)?spring", lower) else "Fall",
                "max_terms": int(term_match.group(1)) if term_match else 8,
            }

        if any(phrase in lower for phrase in ("can i take", "eligible", "am i ready", "qualify")) and codes:
            target_match = re.search(r"(?:take|for|ready for|qualify for)\s+([a-z]{2,5}\s?-?\d{3})", question, re.IGNORECASE)
            target = _codes(target_match.group(1))[0] if target_match else codes[0]
            completed = [code for code in codes if code != target]
            return "prerequisite_check", {"course_code": target, "completed_courses": completed}

        if any(phrase in lower for phrase in ("learning path", "path to", "roadmap", "prepare for", "reach ")) and codes:
            goal = codes[-1]
            completed = codes[:-1] if "from" in lower or "completed" in lower else []
            return "learning_path", {"goal_course": goal, "completed_courses": completed}

        if any(phrase in lower for phrase in ("between", "connect", "connection")) and len(codes) >= 2:
            return "graph_query", {"query_id": "shortest_path", "params": {"from_code": codes[0], "to_code": codes[1]}}

        if "unlock" in lower and codes:
            return "graph_query", {"query_id": "unlocks", "params": {"code": codes[0]}}

        if any(phrase in lower for phrase in ("prerequisite", "required before", "requirements for")) and codes:
            return "graph_query", {"query_id": "prerequisites", "params": {"code": codes[-1]}}

        if any(phrase in lower for phrase in ("source", "catalog entry", "citation")) and codes:
            return "source_retrieval", {"course_codes": codes}

        if "department" in lower and department_match:
            return "graph_query", {
                "query_id": "courses_by_department",
                "params": {"department": department_match.group(1).upper(), "level_min": int(level_match.group(1)) if level_match else 0},
            }

        return "course_search", {
            "query": question,
            "department": department_match.group(1).upper() if department_match and "department" not in lower else None,
            "level": int(level_match.group(1)) if level_match else None,
            "limit": 8,
        }

    def _plan(self, state: AgentState) -> dict[str, Any]:
        question = state["question"]
        if self._model_with_tools is not None:
            try:
                prompt = (
                    "You are CourseGraph Assistant, an expert university course advisor. "
                    "Analyze the user question and invoke the single most appropriate tool to retrieve "
                    "catalog evidence, prerequisite graphs, or degree plans.\n\n"
                    f"User Query: {question}"
                )
                ai_msg = self._model_with_tools.invoke(prompt)
                if ai_msg.tool_calls:
                    call = ai_msg.tool_calls[0]
                    name = call["name"]
                    arguments = call["args"]
                    message = AIMessage(
                        content="",
                        tool_calls=[{"name": name, "args": arguments, "id": "primary-tool-call", "type": "tool_call"}],
                    )
                    return {
                        "messages": [message],
                        "phase": "primary",
                        "selected_tool": name,
                        "selected_arguments": arguments,
                        "tool_trace": [{"tool": name, "status": "called", "arguments": arguments}],
                    }
            except Exception:
                pass

        name, arguments = self._route(question)
        message = AIMessage(
            content="",
            tool_calls=[{"name": name, "args": arguments, "id": "primary-tool-call", "type": "tool_call"}],
        )
        return {
            "messages": [message],
            "phase": "primary",
            "selected_tool": name,
            "selected_arguments": arguments,
            "tool_trace": [{"tool": name, "status": "called", "arguments": arguments}],
        }

    @staticmethod
    def _after_tools(state: AgentState) -> str:
        return "finalize" if state.get("phase") == "verify" else "synthesize"

    def _synthesize(self, state: AgentState) -> dict[str, Any]:
        result = _last_tool_payload(state["messages"])
        if result.get("error") and not result.get("citations"):
            overview = self.repository.get_source("catalog:overview")
            if overview:
                result.update(
                    {
                        "evidence_course_codes": ["CATALOG"],
                        "citations": [
                            {
                                "source_id": overview.id,
                                "title": overview.title,
                                "url": overview.url,
                                "excerpt": overview.excerpt,
                                "supports": ["CATALOG"],
                            }
                        ],
                        "graph_paths": [
                            {
                                "nodes": ["CATALOG", "catalog:overview"],
                                "relationships": ["HAS_SOURCE"],
                                "description": "Catalog error provenance",
                            }
                        ],
                    }
                )

        citations = result.get("citations", [])
        paths = result.get("graph_paths", [])
        markers = _citation_markers(citations)
        answer: str | None = None

        if self.llm is not None and not result.get("error") and citations:
            try:
                synth_prompt = (
                    "You are CourseGraph Assistant, an expert university academic advisor. "
                    "Synthesize an informative, encouraging, and accurate answer for the student based on the tool result.\n"
                    "CRITICAL GROUNDING REQUIREMENT: Every statement must be supported by the citations. "
                    f"You MUST include ALL of the following citation markers in your response: {markers}.\n"
                    "Do not alter the bracketed citation format [catalog:...].\n\n"
                    f"Question: {state['question']}\n"
                    f"Tool Result: {json.dumps(result, default=str)}"
                )
                response = self.llm.invoke(synth_prompt)
                candidate = response.content if isinstance(response.content, str) else str(response.content)
                missing = [
                    item["source_id"]
                    for item in citations
                    if item.get("source_id") and f"[{item['source_id']}]" not in candidate
                ]
                if missing:
                    candidate = f"{candidate}\n\nEvidence: {' '.join(f'[{m}]' for m in missing)}"
                answer = candidate
            except Exception:
                answer = None

        if not answer:
            answer = _format_answer(result)

        verify_args = {"answer": answer, "citations": citations, "graph_paths": paths}
        verify_call = AIMessage(
            content="",
            tool_calls=[{"name": "answer_verification", "args": verify_args, "id": "verification-tool-call", "type": "tool_call"}],
        )
        trace = [*state.get("tool_trace", [])]
        trace[-1]["status"] = "success" if not result.get("error") else "error"
        trace.append(
            {
                "tool": "answer_verification",
                "status": "called",
                "arguments": {"citation_count": len(citations), "path_count": len(paths)},
            }
        )
        return {
            "messages": [verify_call],
            "phase": "verify",
            "result": result,
            "answer": answer,
            "citations": citations,
            "graph_paths": paths,
            "evidence_course_codes": result.get("evidence_course_codes", []),
            "tool_trace": trace,
        }

    @staticmethod
    def _finalize(state: AgentState) -> dict[str, Any]:
        verification = _last_tool_payload(state["messages"])
        trace = [*state.get("tool_trace", [])]
        trace[-1]["status"] = "success" if verification.get("verified") else "failed"
        return {
            "verified": bool(verification.get("verified")),
            "verification_issues": list(verification.get("issues", ["Verification tool failed"])),
            "tool_trace": trace,
        }

    def ask(self, question: str) -> AgentResponse:
        started = time.perf_counter()
        state = self.graph.invoke({"question": question, "messages": [], "tool_trace": []})
        latency_ms = (time.perf_counter() - started) * 1000
        return AgentResponse(
            question=question,
            answer=state["answer"],
            citations=[Citation(**item) for item in state.get("citations", [])],
            graph_paths=[GraphPath(**item) for item in state.get("graph_paths", [])],
            evidence_course_codes=state.get("evidence_course_codes", []),
            verified=state.get("verified", False),
            verification_issues=state.get("verification_issues", []),
            tool_trace=[ToolTrace(**item) for item in state.get("tool_trace", [])],
            latency_ms=round(latency_ms, 2),
        )

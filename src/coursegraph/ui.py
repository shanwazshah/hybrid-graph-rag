from __future__ import annotations

import os

import requests
import streamlit as st


API_URL = os.getenv("COURSEGRAPH_API_URL", "http://localhost:8000").rstrip("/")
EXAMPLES = [
    "Create an 8-semester degree plan with 15 credits per term",
    "What if I delay CS201?",
    "What is the learning path to AI302?",
    "Can I take AI302 if I completed AI201 and AI210?",
    "Find courses about knowledge graphs",
    "What connects MATH210 and AI310?",
    "Which courses does CS204 unlock?",
]

st.set_page_config(page_title="CourseGraph Agent", page_icon="🕸️", layout="wide")
st.markdown(
    """
    <style>
      .block-container {max-width: 1180px; padding-top: 2rem;}
      [data-testid="stMetric"] {background:#111827; border:1px solid #26324a; padding:12px; border-radius:14px;}
      .cg-kicker {color:#7dd3fc; font-weight:700; letter-spacing:.12em; text-transform:uppercase; font-size:.78rem;}
      .cg-title {font-size:3rem; line-height:1.05; font-weight:800; margin:.2rem 0 .5rem;}
      .cg-sub {color:#a8b3cf; max-width:760px; font-size:1.05rem; margin-bottom:1.6rem;}
      .path-card {background:#0b1220; border:1px solid #243149; border-radius:12px; padding:12px 16px; margin:8px 0;}
      .node {color:#e0f2fe; font-weight:700;} .edge {color:#67e8f9; padding:0 6px;}
      .source-card {border-left:3px solid #22d3ee; padding:8px 14px; margin:8px 0; background:#0c1525;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="cg-kicker">Vectorless graph RAG</div>', unsafe_allow_html=True)
st.markdown('<div class="cg-title">CourseGraph Agent</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="cg-sub">Explore courses, verify prerequisites, build constraint-aware semester plans, and simulate delays. '
    'Every response is grounded in catalog sources and a visible graph traversal—no embeddings required.</div>',
    unsafe_allow_html=True,
)

@st.cache_resource
def get_agent():
    from coursegraph.agent import CourseGraphAgent
    from coursegraph.repository import InMemoryGraphRepository

    return CourseGraphAgent(InMemoryGraphRepository())


with st.sidebar:
    st.header("Try an example")
    selected = st.radio("Questions", EXAMPLES, label_visibility="collapsed")
    use_example = st.button("Use this question", use_container_width=True)
    st.divider()
    st.subheader("Quick degree plan")
    credit_cap = st.slider("Maximum credits per term", 9, 18, 15, 3)
    start_term = st.selectbox("Starting term", ["Fall", "Spring"])
    completed_text = st.text_input("Completed course codes", placeholder="CS101, MATH101")
    build_plan = st.button("Build 8-semester plan", use_container_width=True)
    st.divider()
    st.caption("Stack")
    st.markdown("**FastAPI · LangGraph · Neo4j · Streamlit**")
    try:
        status = requests.get(f"{API_URL}/health", timeout=1.5).json()
        st.success(f"Graph online · {status['graph']}")
        api_available = True
    except requests.RequestException:
        st.info("Standalone mode · In-Memory Graph")
        api_available = False

if use_example:
    st.session_state["question"] = selected
if build_plan:
    completed_phrase = f" after completing {completed_text}" if completed_text.strip() else ""
    st.session_state["question"] = (
        f"Create an 8-semester degree plan with {credit_cap} credits per term "
        f"starting in {start_term}{completed_phrase}"
    )

question = st.text_input(
    "Ask about the catalog",
    key="question",
    placeholder="e.g. What path should I follow to reach Generative AI Systems?",
)
ask = st.button("Trace the graph", type="primary", use_container_width=True)

def render_graph_dag_svg(graph_paths: list[dict[str, Any]]) -> str:
    """Generate an interactive SVG network diagram from graph paths."""
    nodes = list(dict.fromkeys(node for path in graph_paths for node in path.get("nodes", [])))
    if not nodes:
        return ""

    edges = []
    seen_edges = set()
    for path in graph_paths:
        p_nodes = path.get("nodes", [])
        p_rels = path.get("relationships", [])
        for i in range(len(p_rels)):
            if i + 1 < len(p_nodes):
                u, rel, v = p_nodes[i], p_rels[i], p_nodes[i + 1]
                edge_key = (u, rel, v)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append(edge_key)

    in_degree = {n: 0 for n in nodes}
    for u, _, v in edges:
        if v in in_degree:
            in_degree[v] += 1

    layers: list[list[str]] = []
    visited: set[str] = set()
    current_layer = [n for n in nodes if in_degree[n] == 0] or [nodes[0]]
    while current_layer:
        layers.append(current_layer)
        visited.update(current_layer)
        next_layer = []
        for u in current_layer:
            for src, _, dst in edges:
                if src == u and dst in nodes and dst not in visited and dst not in next_layer:
                    next_layer.append(dst)
        current_layer = next_layer

    remaining = [n for n in nodes if n not in visited]
    if remaining:
        layers.append(remaining)

    col_width = 160
    row_height = 65
    width = max(len(layers) * col_width + 80, 520)
    max_in_layer = max((len(layer) for layer in layers), default=1)
    height = max(max_in_layer * row_height + 60, 200)

    pos: dict[str, tuple[int, int]] = {}
    for col_idx, layer in enumerate(layers):
        x = 60 + col_idx * col_width
        y_offset = (height - len(layer) * row_height) // 2 + 30
        for row_idx, node in enumerate(layer):
            y = y_offset + row_idx * row_height
            pos[node] = (x, y)

    svg_elements = [
        f'<div style="overflow-x:auto; margin:10px 0;"><svg viewBox="0 0 {width} {height}" style="width:100%; min-width:480px; border-radius:12px; background:#080e1a; border:1px solid #1e293b; padding:10px;">',
        '<defs>',
        '  <marker id="arr" viewBox="0 0 10 10" refX="24" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">',
        '    <path d="M 0 0 L 10 5 L 0 10 z" fill="#38bdf8" />',
        '  </marker>',
        '  <linearGradient id="grad-node" x1="0%" y1="0%" x2="100%" y2="100%">',
        '    <stop offset="0%" stop-color="#1e293b" />',
        '    <stop offset="100%" stop-color="#0f172a" />',
        '  </linearGradient>',
        '</defs>',
    ]

    for u, rel, v in edges:
        if u in pos and v in pos:
            x1, y1 = pos[u]
            x2, y2 = pos[v]
            cx = (x1 + x2) // 2
            svg_elements.append(
                f'<path d="M {x1} {y1} C {cx} {y1}, {cx} {y2}, {x2} {y2}" fill="none" stroke="#38bdf8" stroke-width="2" stroke-opacity="0.85" marker-end="url(#arr)" />'
            )
            mx = (x1 + x2) // 2
            my = (y1 + y2) // 2 - 6
            svg_elements.append(
                f'<text x="{mx}" y="{my}" fill="#94a3b8" font-size="9" text-anchor="middle" font-family="sans-serif">{rel}</text>'
            )

    for node, (x, y) in pos.items():
        is_goal = node == nodes[-1] and len(nodes) > 1
        border_color = "#f59e0b" if is_goal else "#38bdf8" if len(node) <= 8 else "#a855f7"
        text_color = "#fbbf24" if is_goal else "#e0f2fe"
        svg_elements.append(
            f'<g class="node-g" transform="translate({x - 45}, {y - 18})">'
            f'  <rect width="90" height="36" rx="8" fill="url(#grad-node)" stroke="{border_color}" stroke-width="1.8" />'
            f'  <text x="45" y="22" fill="{text_color}" font-weight="bold" font-size="12" text-anchor="middle" font-family="sans-serif">{node}</text>'
            f'</g>'
        )

    svg_elements.append('</svg></div>')
    return "".join(svg_elements)


if ask and question:
    with st.spinner("Searching catalog text and traversing prerequisites…"):
        data = None
        if api_available:
            try:
                response = requests.post(f"{API_URL}/agent/query", json={"question": question}, timeout=15)
                if response.status_code == 200:
                    data = response.json()
            except requests.RequestException:
                data = None

        if data is None:
            agent = get_agent()
            resp = agent.ask(question)
            data = resp.model_dump()

    metric_a, metric_b, metric_c = st.columns(3)
    metric_a.metric("Verified", "Yes" if data["verified"] else "Needs review")
    metric_b.metric("Sources", len(data["citations"]))
    metric_c.metric("Latency", f"{data['latency_ms']:.0f} ms")

    st.subheader("Answer")
    st.markdown(data["answer"])
    if data["verification_issues"]:
        st.warning(" · ".join(data["verification_issues"]))

    left, right = st.columns([1.25, 1])
    with left:
        st.subheader("Supporting graph evidence")
        tab_visual, tab_paths = st.tabs(["Visual Graph DAG", "Path Details"])
        with tab_visual:
            svg_dag = render_graph_dag_svg(data["graph_paths"])
            if svg_dag:
                st.markdown(svg_dag, unsafe_allow_html=True)
            else:
                st.caption("No graph paths to visualize.")
        with tab_paths:
            for path in data["graph_paths"]:
                nodes = path["nodes"]
                relationships = path["relationships"]
                pieces = []
                for index, node in enumerate(nodes):
                    pieces.append(f'<span class="node">{node}</span>')
                    if index < len(relationships):
                        pieces.append(f'<span class="edge">—{relationships[index]}→</span>')
                st.markdown(f'<div class="path-card">{" ".join(pieces)}</div>', unsafe_allow_html=True)
    with right:
        st.subheader("Catalog citations")
        for citation in data["citations"]:
            st.markdown(
                f'<div class="source-card"><b><a href="{citation["url"]}">{citation["source_id"]}</a></b><br>'
                f'<small>{citation["excerpt"]}</small></div>',
                unsafe_allow_html=True,
            )

    with st.expander("Agent tool trace"):
        st.json(data["tool_trace"])
else:
    st.info("Choose an example or ask your own course-planning question.")


import streamlit as st
import plotly.graph_objects as go
import math
import time

# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="AirGraph Assist",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================================================
# CSS — aerospace dark theme, clean and readable
# =========================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
}
.hero {
    background: linear-gradient(135deg, #071628 0%, #0b2240 60%, #0a2e50 100%);
    border: 1px solid #163d6b;
    border-radius: 16px;
    padding: 26px 30px;
    margin-bottom: 20px;
}
.hero-title {
    font-size: 1.9rem;
    font-weight: 600;
    color: #e8f2ff;
    letter-spacing: -0.02em;
    font-family: "JetBrains Mono", monospace;
}
.hero-tag {
    display: inline-block;
    background: rgba(59,130,246,0.15);
    border: 1px solid rgba(59,130,246,0.3);
    border-radius: 999px;
    color: #7bb8f8;
    font-size: 0.78rem;
    padding: 3px 10px;
    margin: 8px 4px 0 0;
    font-family: "JetBrains Mono", monospace;
}
.metric-card {
    background: #0a1e35;
    border: 1px solid #163d6b;
    border-radius: 12px;
    padding: 14px 16px;
    text-align: center;
}
.metric-label {
    color: #4d7fa8;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-family: "JetBrains Mono", monospace;
}
.metric-val {
    font-size: 1.1rem;
    font-weight: 600;
    color: #60a5fa;
    margin-top: 6px;
    font-family: "JetBrains Mono", monospace;
}
/* Step tracker rows */
.step-row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 8px 0;
    border-bottom: 1px solid #0e2a45;
}
.step-icon { font-size: 1.1rem; min-width: 24px; }
.step-name { font-weight: 600; color: #d0e4f8; font-size: 0.88rem; }
.step-desc { color: #5a8bb0; font-size: 0.78rem; margin-top: 2px; line-height: 1.4; }
/* Legend */
.legend-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 0;
    border-bottom: 1px solid #0e2a45;
}
.legend-dot  { width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; }
.legend-name { font-weight: 600; font-size: 0.84rem; color: #d0e4f8; min-width: 148px; }
.legend-desc { color: #5a8bb0; font-size: 0.8rem; }
.edge-legend-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 0;
    border-bottom: 1px solid #0e2a45;
}
.edge-line { width: 22px; height: 2px; border-radius: 1px; flex-shrink: 0; }
/* Chat messages */
[data-testid="stChatMessage"] {
    background: rgba(10, 28, 50, 0.55);
    border: 1px solid #163d6b;
    border-radius: 14px;
}
/* Section heading */
.section-head {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #4d7fa8;
    margin: 16px 0 8px 0;
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# CONSTANTS
# =========================================================

NODE_COLORS = {
    "Component":       "#3b82f6",   # blue
    "Warning":         "#ef4444",   # red
    "Tool":            "#f59e0b",   # amber
    "Defect":          "#f97316",   # orange
    "Requirement":     "#a78bfa",   # purple
    "MaintenanceStep": "#34d399",   # green
    "Node":            "#64748b",   # gray fallback
}

NODE_ICONS = {
    "Component":       "⚙️",
    "Warning":         "⚠️",
    "Tool":            "🔧",
    "Defect":          "🔴",
    "Requirement":     "📋",
    "MaintenanceStep": "📝",
    "Node":            "●",
}

NODE_DESCRIPTIONS = {
    "Component":       "Physical aircraft part — engine, valve, pump, sensor, cable",
    "Warning":         "Safety-critical alert — must be read before performing any work",
    "Tool":            "Equipment required to carry out a maintenance step",
    "Defect":          "Known fault or failure mode documented in the manual",
    "Requirement":     "Airworthiness limitation or regulatory requirement (JAR/EASA)",
    "MaintenanceStep": "A specific numbered procedure step from the maintenance manual",
}

EDGE_COLORS = {
    "USED_IN":       "#3b82f6",
    "REQUIRES_TOOL": "#f59e0b",
    "WARNS_ABOUT":   "#ef4444",
    "FIXES_DEFECT":  "#f97316",
    "GOVERNS":       "#a78bfa",
    "CONNECTED_TO":  "#64748b",
}

EDGE_DESCRIPTIONS = {
    "USED_IN":       "This component is referenced inside the maintenance step",
    "REQUIRES_TOOL": "This procedure step needs the connected tool",
    "WARNS_ABOUT":   "This warning applies to the connected step or component",
    "FIXES_DEFECT":  "Performing this step resolves the connected defect",
    "GOVERNS":       "This airworthiness requirement applies to the component",
    "CONNECTED_TO":  "General documented relationship between two entities",
}

SAMPLE_QUESTIONS = [
    "What maintenance steps are required for the ROTAX 912S engine?",
    "Which components are connected to the fuel system?",
    "Show all safety warnings related to engine maintenance.",
    "What tools are needed for hydraulic system inspection?",
    "List airworthiness limitations for the Aquila AT01 aircraft.",
]

PIPELINE_STEPS = [
    ("🔍", "Entity Extraction",
     "Searches the Neo4j fulltext index for component IDs, system names, "
     "and ATA codes mentioned in your query"),
    ("🕸️", "Graph Traversal",
     "Follows typed edges up to 2 hops from each matched entity, collecting "
     "related components, warnings, tools, and requirements"),
    ("🗜️", "Context Compression",
     "Ranks nodes by type priority (Warning > Requirement > Step > Component > Tool) "
     "and trims to the 2 048-token budget"),
    ("🤖", "LLM Generation",
     "Mistral 7B reasons over the structured graph context and produces "
     "a grounded, source-attributed answer"),
]

# =========================================================
# SESSION STATE
# =========================================================

for key, default in [
    ("messages",      []),
    ("last_result",   None),
    ("pending_query", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# =========================================================
# PIPELINE LOADER
# =========================================================

@st.cache_resource(show_spinner=False)
def load_pipeline():
    """Cache the pipeline singleton — loaded once, reused across all queries."""
    from pipeline import query as pipeline_fn
    return pipeline_fn



# =========================================================
# GRAPH VISUALIZATION
# =========================================================

def render_graph(viz: dict) -> None:
    """
    Render the knowledge subgraph with:
    - Nodes colored by entity type (Component=blue, Warning=red, …)
    - Edges colored by relationship type with inline labels
    - Concentric ring layout (root at centre, others on 2 rings)
    - Rich hover tooltips per node
    - Legend rendered via Plotly (no extra Streamlit elements needed)

    BUG FIX B2: edge labels were completely missing — only bare grey lines.
    BUG FIX B3: all nodes were the same color — type distinction was lost.
    BUG FIX B5: DivisionByZero when graph returned exactly 1 node.
    """
    if not viz or not viz.get("nodes"):
        st.info("No graph data yet — run a query to see the knowledge subgraph.")
        return

    nodes = viz.get("nodes", [])
    edges = viz.get("edges", [])
    root_id = nodes[0]["id"] if nodes else None

    # ── Layout: concentric rings ──────────────────────────────────────────────
    positions: dict[str, tuple[float, float]] = {}

    if nodes:
        positions[nodes[0]["id"]] = (0.0, 0.0)

    inner_nodes = nodes[1:min(7, len(nodes))]
    outer_nodes = nodes[7:]

    for i, node in enumerate(inner_nodes):
        # BUG FIX B5: max(..., 1) prevents ZeroDivisionError with 1 node
        angle = (2 * math.pi * i) / max(len(inner_nodes), 1)
        positions[node["id"]] = (math.cos(angle) * 2.6, math.sin(angle) * 2.6)

    for i, node in enumerate(outer_nodes):
        # Offset outer ring by half-step so nodes don't line up radially
        offset = math.pi / max(len(outer_nodes), 1)
        angle  = (2 * math.pi * i) / max(len(outer_nodes), 1) + offset
        positions[node["id"]] = (math.cos(angle) * 4.8, math.sin(angle) * 4.8)

    fig = go.Figure()

    # ── Edges grouped by relationship type ────────────────────────────────────
    edge_groups: dict[str, list] = {}
    for e in edges:
        lbl = e.get("label", "CONNECTED_TO")
        edge_groups.setdefault(lbl, []).append(e)

    for rel_type, rel_edges in edge_groups.items():
        ex, ey = [], []
        mid_points: list[tuple[float, float]] = []

        for e in rel_edges:
            src, tgt = e.get("from"), e.get("to")
            if src not in positions or tgt not in positions:
                continue
            x0, y0 = positions[src]
            x1, y1 = positions[tgt]
            ex.extend([x0, x1, None])
            ey.extend([y0, y1, None])
            mid_points.append(((x0 + x1) / 2, (y0 + y1) / 2))

        if not ex:
            continue

        color = EDGE_COLORS.get(rel_type, "#64748b")
        fig.add_trace(go.Scatter(
            x=ex, y=ey,
            mode="lines",
            line=dict(width=1.5, color=color),
            hoverinfo="none",
            showlegend=True,
            name=rel_type,
            legendgroup=f"edge_{rel_type}",
            legendgrouptitle=None,
        ))

        # BUG FIX B2: edge label at midpoint of each edge
        # Only show labels when graph is not too dense to avoid clutter
        if len(edges) <= 20:
            for mx, my in mid_points:
                fig.add_annotation(
                    x=mx, y=my,
                    text=rel_type.replace("_", " "),
                    showarrow=False,
                    font=dict(size=7, color=color, family="JetBrains Mono"),
                    bgcolor="rgba(7,16,28,0.82)",
                    borderpad=2,
                    opacity=0.9,
                )

    # ── Nodes grouped by type for colored legend ───────────────────────────────
    node_type_groups: dict[str, list] = {}
    for n in nodes:
        ntype = n.get("type") or "Node"
        node_type_groups.setdefault(ntype, []).append(n)

    for ntype, group in node_type_groups.items():
        nx_list, ny_list, texts, hovers, sizes = [], [], [], [], []
        color = NODE_COLORS.get(ntype, "#64748b")
        icon  = NODE_ICONS.get(ntype, "●")
        desc  = NODE_DESCRIPTIONS.get(ntype, "")

        for n in group:
            nid = n.get("id")
            if not nid or nid not in positions:
                continue
            nx_list.append(positions[nid][0])
            ny_list.append(positions[nid][1])

            label = n.get("label") or nid
            texts.append(label[:16] + "…" if len(label) > 16 else label)

            hovers.append(
                f"<b>{icon} {ntype}</b><br>"
                f"<b>ID:</b> {nid}<br>"
                f"<b>Name:</b> {n.get('label', nid)}<br>"
                f"<br><i>{desc}</i>"
            )
            # Root node is larger; Warnings are slightly larger for visibility
            if nid == root_id:
                sizes.append(26)
            elif ntype == "Warning":
                sizes.append(20)
            else:
                sizes.append(15)

        if not nx_list:
            continue

        fig.add_trace(go.Scatter(
            x=nx_list, y=ny_list,
            mode="markers+text",
            text=texts,
            textposition="top center",
            textfont=dict(size=8.5, color="#c8ddf5", family="IBM Plex Sans"),
            hovertext=hovers,
            hoverinfo="text",
            marker=dict(
                size=sizes,
                color=color,
                opacity=0.92,
                line=dict(width=1.5, color="rgba(255,255,255,0.4)"),
            ),
            name=f"{icon} {ntype}",
            legendgroup=f"node_{ntype}",
            showlegend=True,
        ))

    n_nodes = len(nodes)
    n_edges = len(edges)

    fig.update_layout(
        height=430,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(5,14,26,0.97)",
        showlegend=True,
        legend=dict(
            bgcolor="rgba(5,14,26,0.88)",
            bordercolor="#163d6b",
            borderwidth=1,
            font=dict(color="#c8ddf5", size=10, family="IBM Plex Sans"),
            orientation="h",
            yanchor="bottom",
            y=-0.38,
            xanchor="left",
            x=0,
            traceorder="normal",
        ),
        xaxis=dict(visible=False, scaleanchor="y"),
        yaxis=dict(visible=False),
        margin=dict(l=8, r=8, t=8, b=90),
        hoverlabel=dict(
            bgcolor="#071628",
            bordercolor="#163d6b",
            font=dict(color="#e8f2ff", size=12, family="IBM Plex Sans"),
        ),
    )

    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"**{n_nodes}** nodes · **{n_edges}** relationships — hover any node for details")


# =========================================================
# TIMING CHART
# =========================================================

def render_latency(timing: dict) -> None:
    """
    Bar chart of per-step timing.
    Bars are color-coded: green < 5 s, amber < 30 s, red ≥ 30 s.
    Non-ms keys (like fallback_used) are shown as status badges, not bars.
    """
    if not timing:
        st.info("No timing data yet — run a query first.")
        return

    FRIENDLY = {
        "total_ms":           "⏱ Total pipeline",
        "llm_generation_ms":  "🤖 LLM generation",
    }

    labels, values, colors_list, text_labels = [], [], [], []

    for k, v in timing.items():
        if not k.endswith("_ms"):
            continue
        friendly = FRIENDLY.get(k, k.replace("_ms", "").replace("_", " ").title())
        labels.append(friendly)
        ms = float(v)
        values.append(ms)
        text_labels.append(f"{ms/1000:.1f} s" if ms >= 1000 else f"{ms:.0f} ms")
        colors_list.append(
            "#ef4444" if ms >= 30_000 else
            "#f59e0b" if ms >= 5_000  else
            "#34d399"
        )

    if not labels:
        st.info("No timing keys found.")
        return

    fig = go.Figure(go.Bar(
        x=values,
        y=labels,
        orientation="h",
        text=text_labels,
        textposition="outside",
        marker_color=colors_list,
        textfont=dict(color="#c8ddf5", size=12, family="JetBrains Mono"),
    ))
    fig.update_layout(
        height=max(160, len(labels) * 56),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(5,14,26,0.97)",
        font=dict(color="#c8ddf5", family="IBM Plex Sans"),
        xaxis=dict(
            title="milliseconds",
            color="#4d7fa8",
            gridcolor="#0e2a45",
            tickfont=dict(family="JetBrains Mono", size=10),
        ),
        yaxis=dict(color="#c8ddf5", tickfont=dict(size=12)),
        margin=dict(l=8, r=70, t=8, b=8),
    )
    st.plotly_chart(fig, use_container_width=True)

    col_a, col_b = st.columns(2)
    with col_a:
        if timing.get("fallback_used"):
            st.warning("⚡ Document fallback was used — graph results were sparse for this query.")
        else:
            st.success("✅ Answer sourced entirely from the knowledge graph.")
    with col_b:
        total = timing.get("total_ms", 0)
        llm   = timing.get("llm_generation_ms", 0)
        if total > 0 and llm > 0:
            graph_pct = round((total - llm) / total * 100)
            llm_pct   = round(llm / total * 100)
            st.info(f"Graph retrieval: **{graph_pct}%** of time · LLM: **{llm_pct}%** of time")


# =========================================================
# NODE + RELATIONSHIP GUIDE (educational)
# =========================================================

def render_node_guide() -> None:
    st.markdown('<div class="section-head">Node types in the knowledge graph</div>', unsafe_allow_html=True)
    st.caption("Every piece of information from the maintenance manual is stored as one of these node types.")

    for ntype, color in NODE_COLORS.items():
        if ntype == "Node":
            continue
        icon = NODE_ICONS.get(ntype, "●")
        desc = NODE_DESCRIPTIONS.get(ntype, "")
        st.markdown(
            f'<div class="legend-row">'
            f'<div class="legend-dot" style="background:{color}"></div>'
            f'<span class="legend-name">{icon} {ntype}</span>'
            f'<span class="legend-desc">{desc}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-head" style="margin-top:20px">Relationship types (graph edges)</div>', unsafe_allow_html=True)
    st.caption("Edges connect nodes and carry the maintenance logic. This is what makes GraphRAG more accurate than simple text search.")

    for etype, color in EDGE_COLORS.items():
        if etype == "CONNECTED_TO":
            continue
        desc = EDGE_DESCRIPTIONS.get(etype, "")
        st.markdown(
            f'<div class="edge-legend-row">'
            f'<div class="edge-line" style="background:{color}"></div>'
            f'<span class="legend-name" style="min-width:148px;font-family:\'JetBrains Mono\',monospace;font-size:0.78rem">{etype}</span>'
            f'<span class="legend-desc">{desc}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-head" style="margin-top:20px">Example chain</div>', unsafe_allow_html=True)
    st.markdown(
        "```\n"
        "Requirement ──GOVERNS──► Component ──USED_IN──► MaintenanceStep\n"
        "                                                       │\n"
        "                                            REQUIRES_TOOL ◄── Tool\n"
        "                                                       │\n"
        "                                             Warning ──WARNS_ABOUT──►┘\n"
        "```\n"
        "A single 2-hop traversal from **ROTAX_912S** retrieves its related steps, "
        "all required tools, all attached warnings, and the airworthiness requirement "
        "that governs it — in one graph query, no text similarity needed."
    )


# =========================================================
# HOW GRAPHRAG WORKS (educational)
# =========================================================

def render_graphrag_explainer() -> None:
    st.markdown("#### What is GraphRAG?")
    st.markdown(
        "Classic RAG (Retrieval-Augmented Generation) splits your documents into text chunks, "
        "converts them to vectors, and finds the *closest* chunk by cosine similarity. "
        "It works for general Q&A but has two problems for maintenance manuals:\n\n"
        "1. **Connections are lost** — a warning that applies to a component lives in a "
        "different chunk from the procedure. Similarity search may miss the link.\n"
        "2. **No relationship type** — you can't ask *why* two pieces of information are related."
    )

    st.markdown("#### How this system works differently")
    steps_html = ""
    for i, (icon, name, desc) in enumerate(PIPELINE_STEPS, 1):
        steps_html += (
            f'<div class="step-row">'
            f'<div class="step-icon">{icon}</div>'
            f'<div>'
            f'<div class="step-name">Step {i} — {name}</div>'
            f'<div class="step-desc">{desc}</div>'
            f'</div></div>'
        )
    st.markdown(steps_html, unsafe_allow_html=True)

    st.markdown("#### Why this gives better answers for maintenance data")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            "**Classic RAG**\n"
            "- Finds similar text\n"
            "- Misses cross-chunk links\n"
            "- No relationship context\n"
            "- Can hallucinate connections\n"
            "- Chunk order matters"
        )
    with col2:
        st.markdown(
            "**GraphRAG (this system)**\n"
            "- Follows explicit typed edges\n"
            "- Guarantees warning retrieval\n"
            "- Knows *why* nodes relate\n"
            "- Traceable to graph nodes\n"
            "- Relationship-aware ranking"
        )

    st.markdown("#### Why answers take 30–90 seconds")
    st.markdown(
        "Your laptop runs the LLM on CPU only (no GPU). Mistral 7B generates roughly "
        "**8 tokens per second** on CPU. A 500-token answer = ~60 seconds. "
        "The graph retrieval itself takes under 1 second — the wait is entirely the LLM. "
        "This is the trade-off for running a high-quality 7B model locally with full privacy."
    )


# =========================================================
# HEADER
# =========================================================

st.markdown(
    '<div class="hero">'
    '<div class="hero-title">✈️ AirGraph Assist</div>'
    '<div style="margin-top:10px">'
    '<span class="hero-tag">Aquila AT01 (A210)</span>'
    '<span class="hero-tag">Neo4j GraphRAG</span>'
    '<span class="hero-tag">claude-haiku-4-5-20251001</span>'
    '<span class="hero-tag">CPU-Optimised</span>'
    '<span class="hero-tag">Multi-Hop Reasoning</span>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

# =========================================================
# METRICS ROW
# =========================================================

c1, c2, c3, c4 = st.columns(4)
for col, (label, val) in zip(
    [c1, c2, c3, c4],
    [
        ("Retrieval engine", "Neo4j GraphRAG"),
        ("Language model",   "claude-haiku-4-5-20251001"),
        ("Graph traversal",  "2-hop multi-hop"),
        ("Hardware mode",    "CPU only"),
    ],
):
    col.markdown(
        f'<div class="metric-card">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-val">{val}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
st.markdown("<br>", unsafe_allow_html=True)

# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.markdown(
        '<div style="font-family:\'JetBrains Mono\',monospace;font-size:1.1rem;'
        'font-weight:600;color:#e8f2ff;padding:4px 0 2px 0">✈️ AirGraph Assist</div>',
        unsafe_allow_html=True,
    )
    st.caption("Aquila AT01 (A210) · Maintenance Intelligence")
    st.divider()

    # ── Sample questions ──────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-head">💡 Sample questions</div>',
        unsafe_allow_html=True,
    )
    st.caption("Click any question to send it instantly")

    for i, q in enumerate(SAMPLE_QUESTIONS):
        # BUG FIX B4: original showed questions as non-interactive HTML divs.
        # Now each is a real button. Click sets pending_query + reruns the page.
        if st.button(q, key=f"sample_{i}", use_container_width=True):
            st.session_state.pending_query = q
            st.rerun()

    st.divider()

    # ── Pipeline diagram ──────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-head">⚙️ Pipeline steps</div>',
        unsafe_allow_html=True,
    )
    steps_html = "".join(
        f'<div class="step-row">'
        f'<div class="step-icon">{icon}</div>'
        f'<div><div class="step-name">{name}</div>'
        f'<div class="step-desc">{desc}</div></div></div>'
        for icon, name, desc in PIPELINE_STEPS
    )
    st.markdown(steps_html, unsafe_allow_html=True)


# =========================================================
# MAIN LAYOUT
# =========================================================

left, right = st.columns([3, 2], gap="large")

# =========================================================
# CHAT PANEL
# =========================================================

with left:
    st.subheader("💬 Maintenance Assistant")

    # Render conversation history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Resolve query from chat box OR sample button click
    # BUG FIX B4: sample buttons set pending_query; we consume it here.
    chat_input   = st.chat_input("Ask an aerospace maintenance question…")
    active_query = chat_input
    if not active_query and st.session_state.pending_query:
        active_query = st.session_state.pending_query
        st.session_state.pending_query = None

    if active_query:
        st.session_state.messages.append({"role": "user", "content": active_query})

        with st.chat_message("user"):
            st.markdown(active_query)

        with st.chat_message("assistant"):

            # ── Real-time pipeline step tracker ───────────────────────────────
            # Uses st.status so the user sees all 4 steps clearly while waiting.
            # Steps show as ⏳ (pending) during the blocking pipeline call, then
            # all update to ✅ (complete) with real data when it returns.
            with st.status("🔍 GraphRAG pipeline running…", expanded=True) as pipe_status:
                s1 = st.empty()
                s2 = st.empty()
                s3 = st.empty()
                s4 = st.empty()

                s1.markdown("⏳ **Step 1 — Entity Extraction** · scanning for component IDs and system names…")
                s2.markdown("⏳ **Step 2 — Graph Traversal** · waiting…")
                s3.markdown("⏳ **Step 3 — Context Compression** · waiting…")
                s4.markdown("⏳ **Step 4 — LLM Generation** · waiting… *(30–90 s on CPU)*")

                result = None
                try:
                    pipeline_fn = load_pipeline()
                    t0          = time.time()
                    result      = pipeline_fn(active_query)
                    wall_ms     = (time.time() - t0) * 1000

                    if not isinstance(result, dict):
                        result = {
                            "answer":    str(result),
                            "timing":    {},
                            "graph_viz": {},
                            "entities":  [],
                        }

                    timing   = result.get("timing", {})
                    entities = result.get("entities", [])
                    viz      = result.get("graph_viz", {})
                    llm_ms   = timing.get("llm_generation_ms", 0)
                    fallback = timing.get("fallback_used", False)
                    n_nodes  = len(viz.get("nodes", []))
                    n_edges  = len(viz.get("edges", []))

                    entity_str = (
                        ", ".join(f"`{e}`" for e in entities[:5])
                        if entities else "none matched"
                    )

                    s1.markdown(f"✅ **Step 1 — Entity Extraction** · {len(entities)} found: {entity_str}")
                    s2.markdown(f"✅ **Step 2 — Graph Traversal** · {n_nodes} nodes, {n_edges} relationships")
                    s3.markdown(
                        f"✅ **Step 3 — Context Compression** · "
                        f"{'graph + document fallback' if fallback else 'graph context only'}"
                    )
                    s4.markdown(f"✅ **Step 4 — LLM Generation** · completed in {llm_ms/1000:.1f} s")

                    pipe_status.update(
                        label=f"✅ Done in {wall_ms/1000:.1f} s",
                        state="complete",
                        expanded=False,
                    )

                except Exception as exc:
                    pipe_status.update(label="❌ Pipeline error", state="error", expanded=True)
                    st.error(f"Error: {exc}")
                    result = None

            if result:
                answer = result.get("answer") or "No answer was returned."

                # BUG FIX B1: original called write_stream(stream_text) — passing
                # the function object instead of the generator. st.write_stream
                # expects a generator (iterable), not a callable.
                # Fixed: define as a generator function and call it with ().
                def token_stream():
                    for word in answer.split(" "):
                        yield word + " "
                        time.sleep(0.015)

                st.write_stream(token_stream())

                st.session_state.last_result = result
                st.session_state.messages.append({"role": "assistant", "content": answer})


# =========================================================
# INTELLIGENCE PANEL
# =========================================================

with right:
    st.subheader("📊 Retrieval Intelligence")

    graph_tab, timing_tab, guide_tab, explainer_tab = st.tabs([
        "🔗 Knowledge Graph",
        "⚡ Step Timing",
        "📖 Node Guide",
        "🧠 How GraphRAG Works",
    ])

    current_result = st.session_state.last_result

    with graph_tab:
        if current_result:
            render_graph(current_result.get("graph_viz", {}))
        else:
            st.info(
                "Run a query to see the knowledge subgraph.\n\n"
                "The graph shows which nodes were retrieved and how they are connected — "
                "this is the exact context sent to the LLM."
            )

    with timing_tab:
        if current_result:
            render_latency(current_result.get("timing", {}))
        else:
            st.info("Run a query to see per-step timing breakdown.")

    with guide_tab:
        render_node_guide()

    with explainer_tab:
        render_graphrag_explainer()


# =========================================================
# FOOTER
# =========================================================

st.divider()
st.caption(
    "AirGraph Assist · Aquila AT01 (A210) Maintenance Intelligence · "
    "Neo4j GraphRAG · Mistral 7B q4_K_M · CPU-optimised"
)
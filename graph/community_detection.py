"""
graph/community.py — Step 5

Louvain community detection + LLM-generated summaries per cluster.

Why community detection matters
--------------------------------
- Dense clusters in a maintenance graph = ATA chapters, subsystems
- Pre-computing a summary per cluster means a global query like
  "summarise all fuel system warnings" is answered from ONE community
  summary node, not from traversing thousands of edges at query time.
- Community nodes in Neo4j become Path 4 in the hybrid retriever.

Algorithm: Louvain (python-louvain) on an undirected projection
           of the entity graph (no Chunk nodes — entity-only view).

Install: pip install python-louvain networkx
"""

import json
import os
import sys
import time
from pathlib import Path
from loguru import logger


sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    DATA_DIR, ENTITIES_FILE, COMMUNITY_FILE,
    COMMUNITY_RESOLUTION, COMMUNITY_MIN_SIZE,
    COMMUNITY_SUMMARY_MODEL, COMMUNITY_SUMMARY_TOKENS,
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    ATA_CHAPTERS,
)

try:
    import networkx as nx
except ImportError:
    print("ERROR: pip install networkx"); sys.exit(1)

try:
    import community as community_louvain
except ImportError:
    print("ERROR: pip install python-louvain"); sys.exit(1)

try:
    import anthropic
except ImportError:
    print("ERROR: pip install anthropic"); sys.exit(1)

try:
    from neo4j import GraphDatabase
except ImportError:
    print("ERROR: pip install neo4j"); sys.exit(1)


# ── Build networkx graph from entities ────────────────────────────────────────

def build_nx_graph(entities: list[dict], relationships: list[dict]) -> nx.Graph:
    """
    Build an undirected NetworkX graph from entities and relationships.
    Excludes Chunk and DocumentSection nodes — entity-only view.
    """
    EXCLUDE_TYPES = {"Chunk", "DocumentSection", "Measurement"}
    G = nx.Graph()

    for ent in entities:
        eid   = ent.get("id","")
        etype = ent.get("type","")
        if not eid or etype in EXCLUDE_TYPES:
            continue
        name = ent.get("name","") or ent.get("text","") or eid
        G.add_node(eid, type=etype, name=name, ata=ent.get("ata","00"))

    entity_ids = set(G.nodes)
    for rel in relationships:
        src   = rel.get("source","")
        tgt   = rel.get("target","")
        rtype = rel.get("type","")
        if src in entity_ids and tgt in entity_ids:
            G.add_edge(src, tgt, type=rtype)

    logger.info(f"NetworkX graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G


# ── Run Louvain ────────────────────────────────────────────────────────────────
def run_louvain(G: nx.Graph) -> dict[str, int]:
    """
    Run Louvain community detection.
    Returns {node_id: community_id} mapping.
    """

    if G.number_of_nodes() == 0:
        return {}

    partition = community_louvain.best_partition(
        G,
        resolution=COMMUNITY_RESOLUTION
    )

    n_comm = len(set(partition.values()))

    logger.info(f"Louvain: {n_comm} communities detected")

    return partition

# ── Generate community summaries with Claude ───────────────────────────────────

def summarize_community(
    client:   anthropic.Anthropic,
    comm_id:  int,
    members:  list[dict],
) -> str:
    """Generate an LLM summary for a community of entities."""

    # Build a readable description of the community members
    lines = []
    by_type: dict[str, list] = {}
    for m in members:
        t = m.get("type","Unknown")
        by_type.setdefault(t, []).append(m)

    for etype, items in sorted(by_type.items()):
        names = [i.get("name","") or i.get("text","") or i.get("id","") for i in items]
        lines.append(f"{etype}s ({len(items)}): {', '.join(names[:8])}")

    member_text = "\n".join(lines)

    prompt = (
        f"The following entities from an aircraft maintenance manual "
        f"(Aquila AT01 A210) form a tightly connected cluster:\n\n"
        f"{member_text}\n\n"
        f"Write a concise 2–4 sentence technical summary of what this cluster "
        f"represents — what system or procedure it covers, and what a "
        f"maintenance technician would find here. Be specific and technical."
    )

    for attempt in range(3):
        try:
            resp = client.messages.create(
                model      = COMMUNITY_SUMMARY_MODEL,
                max_tokens = COMMUNITY_SUMMARY_TOKENS,
                messages   = [{"role":"user","content":prompt}]
            )
            return resp.content[0].text.strip()
        except anthropic.RateLimitError:
            wait = 30 * (attempt + 1)
            logger.warning(f"Rate limited — waiting {wait}s...")
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            if e.status_code == 529:
                time.sleep(60 * (attempt + 1))
            else:
                logger.warning(f"API error: {e}"); break
        except Exception as e:
            logger.warning(f"Summarize error: {e}"); break

    return f"Community {comm_id}: {len(members)} entities across multiple ATA chapters."


# ── Write community nodes to Neo4j ────────────────────────────────────────────

def write_to_neo4j(communities: list[dict]):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            for comm in communities:
                cid   = comm["id"]
                props = {
                    "id":          cid,
                    "size":        comm["size"],
                    "ata_chapters": ",".join(comm["ata_chapters"]),
                    "summary":     comm["summary"],
                    "member_ids":  ",".join(comm["member_ids"][:50]),
                }
                s.run("MERGE (n:Community {id:$id}) SET n += $props",
                      id=cid, props=props)

                # Link member entities to their community
                for mid in comm["member_ids"]:
                    try:
                        s.run("""
                        MATCH (e {id:$eid}), (c:Community {id:$cid})
                        MERGE (e)-[:MEMBER_OF]->(c)
                        """, eid=mid, cid=cid)
                    except Exception: pass

        logger.info(f"Wrote {len(communities)} community nodes to Neo4j")
    finally:
        driver.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def detect_communities():
    if not ENTITIES_FILE.exists():
        logger.error(f"{ENTITIES_FILE} not found — run extractor.py first"); return

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set"); sys.exit(1)

    with open(ENTITIES_FILE, encoding="utf-8") as f:
        data = json.load(f)

    entities      = data.get("entities", [])
    relationships = data.get("relationships", [])

    # Build graph and run Louvain
    G         = build_nx_graph(entities, relationships)
    partition = run_louvain(G)

    if not partition:
        logger.warning("No communities detected — graph may be too sparse")
        return

    # Group nodes by community
    comm_members: dict[int, list] = {}
    ent_map = {e["id"]: e for e in entities}

    for node_id, comm_id in partition.items():
        comm_members.setdefault(comm_id, [])
        if node_id in ent_map:
            comm_members[comm_id].append(ent_map[node_id])

    # Filter tiny communities
    valid_comms = {cid: members
                   for cid, members in comm_members.items()
                   if len(members) >= COMMUNITY_MIN_SIZE}
    logger.info(f"Valid communities (size≥{COMMUNITY_MIN_SIZE}): {len(valid_comms)}")

    # Generate summaries
    client     = anthropic.Anthropic(api_key=api_key)
    output     = []
    sorted_comms = sorted(valid_comms.items(), key=lambda x: -len(x[1]))

    for i, (comm_id, members) in enumerate(sorted_comms, 1):
        ata_set = list(set(m.get("ata","00") for m in members if m.get("ata","00") != "00"))
        ata_set.sort()
        ata_names = [ATA_CHAPTERS.get(a, f"ATA {a}") for a in ata_set[:5]]

        logger.info(f"[{i}/{len(sorted_comms)}] Community {comm_id} "
                    f"({len(members)} nodes, ATAs: {ata_set[:4]})")

        summary = summarize_community(client, comm_id, members)

        output.append({
            "id":           f"COMM-{comm_id:04d}",
            "size":         len(members),
            "ata_chapters": ata_set,
            "ata_names":    ata_names,
            "summary":      summary,
            "member_ids":   [m.get("id","") for m in members],
        })

    # Save
    with open(COMMUNITY_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(output)} community summaries → {COMMUNITY_FILE}")

    # Write to Neo4j
    write_to_neo4j(output)
    logger.info("Communities written to Neo4j")
    logger.info("Next: python pipeline.py (or streamlit run app.py)")


if __name__ == "__main__":
    detect_communities()

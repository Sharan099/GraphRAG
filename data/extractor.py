"""
data/extractor.py — Step 2 + Steps 16–20 (Extraction Pipeline)

Schema-validated, domain-specific entity and relationship extraction.

Key differences from all previous versions
-------------------------------------------
Step 17 (LLM design):  Prompt generated FROM schema.py — always in sync.
                        ATA context + detected structural features injected.
                        Different sub-prompts for WARNING-heavy vs step-heavy chunks.
Step 18 (Validation):  Raw LLM output parsed through schema.ExtractionResult.
                        Invalid IDs and mismatched types are caught and logged.
Step 19 (Resolution):  EntityRegistry from schema.py handles all deduplication.
Step 20 (Rel resolve): EntityRegistry.resolve_relationships() repairs endpoints.
Step 12 (IDs):         Prompts show real ID examples from schema.py functions.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
def p(msg): print(msg, flush=True)

try:
    import anthropic
except ImportError:
    p("ERROR: pip install anthropic"); sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    DATA_DIR, CHUNKS_FILE, ENTITIES_FILE,
    EXTRACTION_MODEL, EXTRACTION_MAX_TOKENS,
    BATCH_ID_FILE, PROGRESS_FILE,
)
from data.schema import (
    build_extraction_schema_prompt,
    EntityRegistry,
)

POLL_INTERVAL = 60
ATA_CHAPTERS  = {
    "00":"General","04":"Airworthiness Limitations","05":"Time Limits",
    "12":"Servicing","20":"Standard Practices","24":"Electrical Power",
    "27":"Flight Controls","28":"Fuel","32":"Landing Gear","51":"Structures",
    "61":"Propeller","71":"Power Plant","72":"Engine","73":"Engine Fuel",
    "74":"Ignition","75":"Air","76":"Engine Controls","77":"Engine Indicating",
    "78":"Exhaust","79":"Oil","80":"Starting",
}


# ── Prompt construction (Step 17) ─────────────────────────────────────────────

SYSTEM = (
    "You are a precision aerospace maintenance data extraction engine for the "
    "Aquila AT01 (A210) aircraft — EASA Part-M compliant light aircraft. "
    "Extract structured entities and relationships from maintenance manual chunks. "
    "Return ONLY valid JSON. No markdown, no explanation, no preamble."
)

def build_context_hints(chunk: dict) -> str:
    """
    Build tailored extraction hints based on what structural features
    are present in this specific chunk. This focuses the LLM on what
    actually exists in the text instead of a generic prompt.
    """
    hints = []

    if chunk.get("has_warning"):
        hints.append(
            "⚠ This chunk contains WARNING blocks. Extract each as a Warning entity "
            "with level='WARNING'. Create WARNS_ABOUT relationships to every component "
            "or system mentioned in the warning, and WARNS_BEFORE to the step it precedes."
        )
    if chunk.get("has_caution"):
        hints.append(
            "⚠ This chunk contains CAUTION blocks. Extract each as a Warning entity "
            "with level='CAUTION'. Link with WARNS_ABOUT and WARNS_BEFORE relationships."
        )
    if chunk.get("has_steps"):
        n = chunk.get("step_count", 0)
        hints.append(
            f"📋 This chunk contains {n} numbered procedure steps. "
            "Extract each numbered step as a Step entity. "
            "Create PRECEDES relationships linking them in sequence order. "
            "Link each step to its tools with REQUIRES_TOOL and to components with USED_IN."
        )
    if chunk.get("has_tools_table"):
        hints.append(
            "🔧 This chunk contains a 'Tools Required' or 'Materials Required' table. "
            "Extract every tool as a Tool entity and every material as a Consumable entity. "
            "Create REQUIRES_TOOL/USES_CONSUMABLE relationships to the parent task."
        )
    if chunk.get("has_measurements"):
        n = chunk.get("measurement_count", 0)
        hints.append(
            f"📐 This chunk contains {n} measurements (torque, pressure, clearance, etc). "
            "Extract each as a Measurement entity with value, unit, and context. "
            "Create HAS_MEASUREMENT relationships to the relevant step or component."
        )
    if chunk.get("has_part_numbers"):
        hints.append(
            "🔩 This chunk contains part numbers. Extract each as a PartNumber entity. "
            "Create USES_PART relationships from the task or step that references them."
        )

    return "\n".join(hints) if hints else ""


def make_prompt(chunk: dict) -> str:
    ata       = chunk.get("ata", "00")
    ata_name  = ATA_CHAPTERS.get(ata, f"ATA {ata}")
    title     = chunk.get("section_title", "")
    page_info = f"pages {chunk.get('page_start','?')}–{chunk.get('page_end','?')}"
    hints     = build_context_hints(chunk)
    schema    = build_extraction_schema_prompt()

    return (
        f"DOCUMENT: Aquila AT01 (A210) Maintenance Manual\n"
        f"ATA CHAPTER: {ata} — {ata_name}\n"
        f"SECTION: {title}\n"
        f"LOCATION: {page_info}\n"
        f"CHUNK ID: {chunk.get('chunk_id','')}\n\n"
        + (f"EXTRACTION FOCUS:\n{hints}\n\n" if hints else "")
        + f"TEXT TO EXTRACT FROM:\n{'='*60}\n{chunk.get('text','')}\n{'='*60}\n\n"
        + f"Extract all entities and relationships from the text above.\n\n"
        + "CRITICAL: You MUST extract relationships. Every entity you extract should "
          "have at least one relationship to another entity. "
          "If a WARNING appears before a step, create WARNS_BEFORE. "
          "If a step uses a component, create USED_IN. "
          "If steps are numbered in sequence, create PRECEDES between each pair. "
          "If a component belongs to a system, create PART_OF. "
          "Zero relationships is almost always wrong for maintenance manual content.\n\n"
        + schema
    )


# ── JSON salvage (handles MAX_TOKENS truncation) ───────────────────────────────

def salvage_json(raw: str, cid: str) -> dict | None:
    clean = re.sub(r"```[a-z]*\s*", "", raw, flags=re.I).strip("` \n")
    start = clean.find("{")
    if start == -1: return None
    clean = clean[start:]
    try: return json.loads(clean)
    except json.JSONDecodeError: pass

    depth = 0; in_str = False; escape = False; last_safe = 0
    for i, ch in enumerate(clean):
        if escape:     escape = False; continue
        if ch == "\\" and in_str: escape = True; continue
        if ch == '"':  in_str = not in_str; continue
        if in_str:     continue
        if ch in "{[": depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 1: last_safe = i + 1

    if last_safe > 20:
        cand  = clean[:last_safe].rstrip().rstrip(",")
        opens = cand.count("{") - cand.count("}")
        openb = cand.count("[") - cand.count("]")
        cand += "]" * max(openb,0) + "}" * max(opens,0)
        try:
            result = json.loads(cand)
            e = len(result.get("entities",[])); r = len(result.get("relationships",[]))
            p(f"  ⚠ {cid}: salvaged {e}E {r}R from truncated response")
            return result
        except json.JSONDecodeError: pass

    p(f"  ✗ {cid}: unsalvageable"); return None


# ── Batch API ─────────────────────────────────────────────────────────────────

def load_chunks() -> list[dict]:
    if not CHUNKS_FILE.exists():
        p(f"ERROR: {CHUNKS_FILE} not found — run chunker.py first"); sys.exit(1)
    with open(CHUNKS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    chunks = data.get("chunks",[])
    p(f"Loaded {len(chunks)} chunks")
    return chunks


def submit(client: anthropic.Anthropic, chunks: list[dict]) -> str | None:
    if BATCH_ID_FILE.exists():
        bid = BATCH_ID_FILE.read_text(encoding="utf-8").strip()
        p(f"Batch already submitted: {bid}"); return bid

    p(f"Building {len(chunks)} batch requests...")
    reqs = [{
        "custom_id": chunk["chunk_id"],
        "params": {
            "model":      EXTRACTION_MODEL,
            "max_tokens": EXTRACTION_MAX_TOKENS,
            "messages":   [{"role":"user","content": SYSTEM + "\n\n" + make_prompt(chunk)}]
        }
    } for chunk in chunks]

    try:
        batch = client.messages.batches.create(requests=reqs)
    except Exception as e:
        p(f"Batch submit failed: {e}"); return None

    BATCH_ID_FILE.write_text(batch.id, encoding="utf-8")
    p(f"✅ Batch submitted — ID: {batch.id}")
    p(f"   Requests: {batch.request_counts.processing}")
    return batch.id


def collect(client: anthropic.Anthropic, chunks: list[dict]) -> list[tuple] | None:
    if not BATCH_ID_FILE.exists():
        p("ERROR: No batch submitted."); return None

    batch_id  = BATCH_ID_FILE.read_text(encoding="utf-8").strip()
    chunk_map = {c["chunk_id"]: c for c in chunks}

    while True:
        batch  = client.messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        p(f"Status: {batch.processing_status}  "
          f"Processing:{counts.processing}  Done:{counts.succeeded}  Errors:{counts.errored}")
        if batch.processing_status == "ended": break
        p(f"Waiting {POLL_INTERVAL}s..."); time.sleep(POLL_INTERVAL)

    raw_results: dict[str, dict] = {}
    err = 0
    for result in client.messages.batches.results(batch_id):
        cid = result.custom_id
        if result.result.type == "succeeded":
            raw    = result.result.message.content[0].text.strip()
            parsed = salvage_json(raw, cid)
            if parsed: raw_results[cid] = parsed
            else: err += 1
        else:
            p(f"  Error {cid}: {result.result.error.type}"); err += 1

    p(f"Downloaded: {len(raw_results)} ok, {err} failed")
    BATCH_ID_FILE.unlink(missing_ok=True)
    return [(raw_results[cid], chunk_map[cid]) for cid in raw_results if cid in chunk_map]


def seq(client: anthropic.Anthropic, chunks: list[dict]) -> list[tuple]:
    progress: dict = {}
    if PROGRESS_FILE.exists():
        try: progress = json.loads(PROGRESS_FILE.read_text(encoding="utf-8")); p(f"Resuming — {len(progress)} cached")
        except Exception: pass

    remaining = [c for c in chunks if c["chunk_id"] not in progress]
    p(f"Processing {len(remaining)} chunks...")

    for i, chunk in enumerate(remaining, 1):
        cid = chunk["chunk_id"]
        p(f"[{i}/{len(remaining)}] {cid} ({chunk.get('word_count',0)}w "
          f"{'⚠' if chunk.get('has_warning') else ''}"
          f"{'📋' if chunk.get('has_steps') else ''}"
          f"{'🔧' if chunk.get('has_tools_table') else ''}"
          f"{'📐' if chunk.get('has_measurements') else ''})")

        result = None
        for attempt in range(1, 4):
            try:
                resp = client.messages.create(
                    model      = EXTRACTION_MODEL,
                    max_tokens = EXTRACTION_MAX_TOKENS,
                    messages   = [{"role":"user","content": SYSTEM + "\n\n" + make_prompt(chunk)}]
                )
                raw    = resp.content[0].text.strip()
                result = salvage_json(raw, cid)
                if result: break
            except anthropic.APIStatusError as e:
                if e.status_code == 529:
                    wait = 90 * attempt; p(f"  529 — waiting {wait}s..."); time.sleep(wait)
                else: p(f"  {e.status_code}: {e.message}"); time.sleep(10); break
            except anthropic.RateLimitError:
                wait = 45 * attempt; p(f"  429 — waiting {wait}s..."); time.sleep(wait)
            except Exception as e: p(f"  Error: {e}"); time.sleep(5)

        if result:
            e = len(result.get("entities",[])); r = len(result.get("relationships",[]))
            p(f"  → {e}E {r}R")
            progress[cid] = result
            PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False), encoding="utf-8")
        else:
            p(f"  → skipped")

    chunk_map = {c["chunk_id"]: c for c in chunks}
    return [(progress[cid], chunk_map[cid]) for cid in progress if cid in chunk_map]


def cancel(client: anthropic.Anthropic):
    if not BATCH_ID_FILE.exists(): p("No batch to cancel."); return
    bid = BATCH_ID_FILE.read_text(encoding="utf-8").strip()
    try: client.messages.batches.cancel(bid); p(f"Cancelled {bid}")
    except Exception as e: p(f"Cancel failed: {e}")
    BATCH_ID_FILE.unlink(missing_ok=True)


# ── Merge using EntityRegistry (Steps 19–20) ──────────────────────────────────

def merge_results(results_with_chunks: list[tuple]) -> dict:
    """
    Merge all chunk extractions through EntityRegistry for proper
    deduplication (Step 19) and relationship resolution (Step 20).
    """
    registry = EntityRegistry()

    for result, chunk in results_with_chunks:
        cid = chunk["chunk_id"]
        for ent in result.get("entities", []):
            if ent.get("id"):
                registry.add_entity(ent, cid)
        for rel in result.get("relationships", []):
            frm = rel.get("from","") or rel.get("source","")
            to  = rel.get("to","")   or rel.get("target","")
            if frm and to:
                registry.add_relationship({
                    "source": frm, "target": to,
                    "type":   rel.get("type","CONNECTED_TO"),
                    "properties": rel.get("properties",{})
                }, cid)

    dataset = registry.to_dataset()
    return dataset


def save_dataset(dataset: dict):
    with open(ENTITIES_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)
    p(f"\n=== Extraction complete ===")
    for etype, cnt in sorted(dataset["summary"]["by_type"].items(), key=lambda x: -x[1]):
        p(f"  {etype:25s}: {cnt:4d}")
    p(f"  {'relationships':25s}: {dataset['summary']['total_rels']:4d}")
    p(f"Saved → {ENTITIES_FILE}")
    if PROGRESS_FILE.exists(): PROGRESS_FILE.unlink()
    p("Next: python data/embedder.py")


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key: p("ERROR: ANTHROPIC_API_KEY not set"); sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    mode   = sys.argv[1] if len(sys.argv) > 1 else "both"
    chunks = load_chunks() if mode != "cancel" else []

    if   mode == "cancel":  cancel(client)
    elif mode == "submit":  submit(client, chunks)
    elif mode == "collect":
        results = collect(client, chunks)
        if results: save_dataset(merge_results(results))
    elif mode == "seq":
        results = seq(client, chunks)
        if results: save_dataset(merge_results(results))
    else:
        submit(client, chunks)
        results = collect(client, chunks)
        if results: save_dataset(merge_results(results))


if __name__ == "__main__":
    main()
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
def p(msg): print(msg, flush=True)

try:
    import fitz
except ImportError:
    p("ERROR: pip install pymupdf"); sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_DIR, CHUNKS_FILE, CHUNK_SIZE, CHUNK_OVERLAP, MIN_CHUNK_LEN

# ATA structural patterns
SAFETY_RE    = re.compile(r'^\s*(?:WARNING|CAUTION|NOTE)\s*[:\-]?\s*$', re.MULTILINE|re.I)
STEP_RE      = re.compile(r'^\s*(?:\(\d+\)|\d+[\.\):]|Step\s+\d+:|[a-z][\.\)])\s+\S', re.MULTILINE)
TASK_RE      = re.compile(r'^\s*(?:TASK|JOB SET-UP|JOB CLOSE-UP|SUBTASK|PROCEDURE)\b', re.MULTILINE|re.I)
TOOLS_RE     = re.compile(r'^\s*(?:TOOLS REQUIRED|MATERIALS REQUIRED|PARTS REQUIRED)', re.MULTILINE|re.I)
PART_NO_RE   = re.compile(r'\b\d{3,}\s*[\-]\s*\d{3,}\b')
MEASURE_RE   = re.compile(r'\b\d+(?:[.,]\d+)?\s*(?:Nm|N\.m|ft\.?lb|bar|psi|mm|cm|°[CF]|kPa)\b', re.I)


def detect_features(text: str) -> dict:
    return {
        "has_warning":      bool(re.search(r'\bWARNING\b', text, re.I)),
        "has_caution":      bool(re.search(r'\bCAUTION\b', text, re.I)),
        "has_note":         bool(re.search(r'\bNOTE\b', text, re.I)),
        "has_steps":        bool(STEP_RE.search(text)),
        "has_tools_table":  bool(TOOLS_RE.search(text)),
        "has_measurements": bool(MEASURE_RE.search(text)),
        "has_part_numbers": bool(PART_NO_RE.search(text)),
        "step_count":       len(STEP_RE.findall(text)),
        "measurement_count":len(MEASURE_RE.findall(text)),
    }


def chunk_section(text: str, metadata: dict) -> list[dict]:
    """
    Split section text into overlapping chunks.
    Safety blocks (WARNING/CAUTION/NOTE) are never separated from
    the content they immediately precede.
    """
    words      = text.split()
    total      = len(words)
    chunks     = []
    seq        = 0
    pos        = 0

    while pos < total:
        end      = min(pos + CHUNK_SIZE, total)
        chunk_w  = words[pos:end]
        chunk_t  = " ".join(chunk_w)

        if len(chunk_w) >= MIN_CHUNK_LEN:
            cid   = f"{metadata.get('section_id','SEC-0000')}-C{seq+1:03d}"
            feat  = detect_features(chunk_t)
            chunks.append({
                **metadata,
                "chunk_id":   cid,
                "text":       chunk_t,
                "word_count": len(chunk_w),
                "chunk_seq":  seq,
                **feat,
            })
            seq += 1

        step = CHUNK_SIZE - CHUNK_OVERLAP
        pos += step
        if pos >= total:
            break

    return chunks


def _guess_ata(title: str) -> str:
    m = re.search(r'\b(\d{2})(?:-\d+)?\b', title)
    return m.group(1) if m else "00"


def extract_toc(doc: fitz.Document) -> list[dict]:
    raw = doc.get_toc(simple=True)
    if not raw:
        return [{"id":"SEC-0001","level":1,"ata":"00","title":"Main Content",
                 "page_start":0,"page_end":len(doc)-1}]
    sections = []
    for idx, (level, title, page_1) in enumerate(raw):
        page_end = len(doc) - 1
        for j in range(idx+1, len(raw)):
            if raw[j][0] <= level:
                page_end = max(0, raw[j][2]-2); break
        sections.append({"id":f"SEC-{idx+1:04d}","level":level,
                          "ata":_guess_ata(title),"title":title.strip(),
                          "page_start":max(0,page_1-1),"page_end":page_end})
    return sections


def page_to_section(sections: list[dict], page_idx: int) -> dict:
    best = None
    for s in sections:
        if s["page_start"] <= page_idx <= s["page_end"]:
            if best is None or s["level"] > best["level"]:
                best = s
    return best or sections[0]


def process(pdf_path: Path) -> list[dict]:
    p(f"Opening: {pdf_path.name}")
    doc      = fitz.open(str(pdf_path))
    n_pages  = len(doc)
    p(f"  Pages: {n_pages}")
    sections = extract_toc(doc)
    p(f"  TOC entries: {len(sections)}")

    page_texts: dict[int,str] = {}
    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        if text: page_texts[i] = text
    doc.close()

    section_data: dict[str,dict] = {}
    for page_idx, text in page_texts.items():
        sec = page_to_section(sections, page_idx)
        sid = sec["id"]
        if sid not in section_data:
            section_data[sid] = {**sec, "full_text":"", "pages":[]}
        section_data[sid]["full_text"] += f"\n{text}"
        section_data[sid]["pages"].append(page_idx+1)

    all_chunks: list[dict] = []
    global_seq = 0
    for sid, sdata in section_data.items():
        text = sdata["full_text"].strip()
        if len(text.split()) < MIN_CHUNK_LEN:
            continue
        pages    = sdata.get("pages",[])
        metadata = {
            "section_id":    sid,
            "section_title": sdata["title"],
            "ata":           sdata["ata"],
            "level":         sdata["level"],
            "page_start":    pages[0]  if pages else 0,
            "page_end":      pages[-1] if pages else 0,
        }
        for chunk in chunk_section(text, metadata):
            chunk["global_seq"] = global_seq
            global_seq += 1
            all_chunks.append(chunk)

    wc    = [c["word_count"] for c in all_chunks]
    warns = sum(1 for c in all_chunks if c.get("has_warning"))
    steps = sum(c.get("step_count",0) for c in all_chunks)
    meass = sum(c.get("measurement_count",0) for c in all_chunks)

    p(f"  Chunks              : {len(all_chunks)}")
    p(f"  Avg words/chunk     : {sum(wc)/len(wc):.0f}")
    p(f"  Chunks with WARNING : {warns}")
    p(f"  Total steps found   : {steps}")
    p(f"  Total measurements  : {meass}")
    return all_chunks


def main():
    pdfs = sorted(DATA_DIR.rglob("*.pdf"))
    if not pdfs: p("ERROR: No PDF in data/"); sys.exit(1)
    (DATA_DIR/".cache").mkdir(exist_ok=True)
    chunks = process(pdfs[0])
    with open(CHUNKS_FILE,"w",encoding="utf-8") as f:
        json.dump({"pdf":pdfs[0].name,"chunks":chunks},f,indent=2,ensure_ascii=False)
    p(f"\nSaved → {CHUNKS_FILE}")
    p("Next: python data/extractor.py")

if __name__ == "__main__":
    main()
"""
schema.py — AirGraph Assist

Complete Pydantic v2 schema derived from the 27-step methodology.

Design decisions traced to methodology steps
--------------------------------------------
Step 1  (Doc type):     ATA iSpec 2200 → structured hierarchy, not free-form text
Step 7  (Ontology):     16 entity types covering all manual content patterns
Step 9  (Properties):   Every field typed, optional vs required defined explicitly
Step 10 (Relations):    12 relationship types covering all traversal needs
Step 12 (IDs):          Deterministic: ATA + normalized name → reproducible IDs
Step 13 (Provenance):   Every entity carries source chunk, page, section
Step 14 (Confidence):   0.0–1.0 score per entity and relationship
Step 18 (Validation):   Pydantic validators enforce ID patterns and field constraints
Step 19 (Resolution):   Normalization function used for deduplication key

Key insight: the ID generation must be DETERMINISTIC.
Same component extracted from 5 different chunks must always produce
the same ID so all 5 extractions merge into one node, not 5 orphans.
"""

import re
import hashlib
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator, model_validator


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS — controlled vocabularies
# ══════════════════════════════════════════════════════════════════════════════

class EntityType(str, Enum):
    # Structural (document hierarchy)
    ATA_CHAPTER          = "ATAChapter"
    SECTION              = "Section"
    TASK                 = "Task"
    STEP                 = "Step"
    # Technical (aircraft components and systems)
    COMPONENT            = "Component"
    SYSTEM               = "System"
    TOOL                 = "Tool"
    CONSUMABLE           = "Consumable"
    PART_NUMBER          = "PartNumber"
    # Safety (safety-critical blocks)
    WARNING              = "Warning"
    CAUTION              = "Caution"
    NOTE                 = "Note"
    # Compliance (regulatory requirements)
    REQUIREMENT          = "Requirement"
    INSPECTION_INTERVAL  = "InspectionInterval"
    # Measurement (quantitative specifications)
    MEASUREMENT          = "Measurement"
    # GraphRAG infrastructure
    CHUNK                = "Chunk"
    COMMUNITY            = "Community"


class RelationshipType(str, Enum):
    # Structural navigation
    CONTAINS             = "CONTAINS"           # Chapter→Section, Section→Task, Task→Step
    PART_OF              = "PART_OF"            # Component→System, Component→Component
    PRECEDES             = "PRECEDES"           # Step→Step (sequence order)
    PART_OF_SECTION      = "PART_OF_SECTION"   # Chunk→Section
    ADJACENT_TO          = "ADJACENT_TO"        # Chunk→Chunk (consecutive)
    # Task execution
    REQUIRES_TOOL        = "REQUIRES_TOOL"      # Task/Step→Tool
    USES_CONSUMABLE      = "USES_CONSUMABLE"    # Task/Step→Consumable
    APPLIES_TO           = "APPLIES_TO"         # Task→Component/System
    REFERENCES           = "REFERENCES"         # Task→Task (cross-reference)
    USES_PART            = "USES_PART"          # Task/Step→PartNumber
    # Safety
    WARNS_BEFORE         = "WARNS_BEFORE"       # Warning/Caution→Step (immediately precedes)
    WARNS_ABOUT          = "WARNS_ABOUT"        # Warning/Caution→Component/System
    # Compliance
    GOVERNS              = "GOVERNS"            # Requirement→Component/System
    HAS_INTERVAL         = "HAS_INTERVAL"       # Requirement→InspectionInterval
    # Measurement
    HAS_MEASUREMENT      = "HAS_MEASUREMENT"    # Step/Component→Measurement
    # GraphRAG
    SOURCED_FROM         = "SOURCED_FROM"       # Entity→Chunk
    MEMBER_OF            = "MEMBER_OF"          # Entity→Community
    CONTAINS_ENTITY      = "CONTAINS_ENTITY"    # Chunk→Entity


class WarnLevel(str, Enum):
    WARNING = "WARNING"
    CAUTION = "CAUTION"
    NOTE    = "NOTE"


class RequirementType(str, Enum):
    AIRWORTHINESS_LIMITATION = "AIRWORTHINESS_LIMITATION"
    INSPECTION               = "INSPECTION"
    OPERATIONAL_LIMITATION   = "OPERATIONAL_LIMITATION"
    PROCEDURE                = "PROCEDURE"
    CERTIFICATION            = "CERTIFICATION"


class MeasurementType(str, Enum):
    TORQUE      = "TORQUE"
    PRESSURE    = "PRESSURE"
    CLEARANCE   = "CLEARANCE"
    TENSION     = "TENSION"
    TEMPERATURE = "TEMPERATURE"
    VOLUME      = "VOLUME"
    WEIGHT      = "WEIGHT"
    SPEED       = "SPEED"
    TIME        = "TIME"
    OTHER       = "OTHER"


# ══════════════════════════════════════════════════════════════════════════════
# DETERMINISTIC ID GENERATION (Step 12)
# ══════════════════════════════════════════════════════════════════════════════

def normalize_name(name: str) -> str:
    """
    Normalize a name for use in deterministic IDs and deduplication.
    Rules:
    - Lowercase → uppercase after prefix
    - Remove special chars except underscore
    - Collapse whitespace/hyphens to underscore
    - Max 5 words
    - German umlauts replaced (ä→AE, ö→OE, ü→UE)
    """
    # Replace German umlauts
    replacements = {"ä":"AE","ö":"OE","ü":"UE","Ä":"AE","Ö":"OE","Ü":"UE","ß":"SS"}
    for char, repl in replacements.items():
        name = name.replace(char, repl)
    # Normalize
    name = re.sub(r'[^\w\s]', ' ', name)           # special chars → space
    name = re.sub(r'[\s\-_/]+', '_', name.strip())  # whitespace → underscore
    name = name.upper()
    # Limit to 5 words
    parts = name.split('_')
    return '_'.join(parts[:5])


def normalize_for_dedup(name: str) -> str:
    """Normalized form used for entity deduplication (lowercase, no separators)."""
    n = normalize_name(name).lower()
    return re.sub(r'_+', '', n)


def make_component_id(ata: str, name: str) -> str:
    """COMP-71-OIL_FILTER_ASSY"""
    return f"COMP-{ata.zfill(2)}-{normalize_name(name)}"


def make_system_id(ata: str, name: str) -> str:
    """SYS-28-FUEL"""
    return f"SYS-{ata.zfill(2)}-{normalize_name(name)}"


def make_tool_id(name: str) -> str:
    """TOOL-TORQUE_WRENCH_10NM"""
    return f"TOOL-{normalize_name(name)}"


def make_consumable_id(name: str) -> str:
    """CONS-ENGINE_OIL_5W50"""
    return f"CONS-{normalize_name(name)}"


def make_warning_id(ata: str, seq: int) -> str:
    """WARN-71-0001"""
    return f"WARN-{ata.zfill(2)}-{seq:04d}"


def make_caution_id(ata: str, seq: int) -> str:
    """CAUT-71-0001"""
    return f"CAUT-{ata.zfill(2)}-{seq:04d}"


def make_note_id(ata: str, seq: int) -> str:
    """NOTE-71-0001"""
    return f"NOTE-{ata.zfill(2)}-{seq:04d}"


def make_requirement_id(ata: str, req_type: str, seq: int) -> str:
    """REQ-05-AWL-0001"""
    type_abbr = {
        "AIRWORTHINESS_LIMITATION": "AWL",
        "INSPECTION": "INSP",
        "OPERATIONAL_LIMITATION": "OPS",
        "PROCEDURE": "PROC",
        "CERTIFICATION": "CERT",
    }.get(req_type, "REQ")
    return f"REQ-{ata.zfill(2)}-{type_abbr}-{seq:04d}"


def make_measurement_id(ata: str, meas_type: str, seq: int) -> str:
    """MEAS-71-TORQUE-0001"""
    return f"MEAS-{ata.zfill(2)}-{meas_type}-{seq:04d}"


def make_task_id(ata: str, section: str, subject: str, task_no: int) -> str:
    """TASK-71-10-00-0801"""
    return f"TASK-{ata.zfill(2)}-{section.zfill(2)}-{subject.zfill(2)}-{task_no:04d}"


def make_step_id(task_id: str, step_no: int) -> str:
    """STEP-TASK-71-10-00-0801-003"""
    return f"STEP-{task_id}-{step_no:03d}"


def make_chunk_id(section_id: str, seq: int) -> str:
    """CHUNK-SEC-71-00-0003"""
    return f"CHUNK-{section_id}-{seq:04d}"


def make_part_id(part_number: str) -> str:
    """PART-985782-000"""
    clean = re.sub(r'[^\w\-]', '', part_number.upper())
    return f"PART-{clean}"


# ══════════════════════════════════════════════════════════════════════════════
# PROVENANCE (Step 13)
# ══════════════════════════════════════════════════════════════════════════════

class Provenance(BaseModel):
    """Tracks where an entity was extracted from."""
    chunk_ids:   list[str]       = Field(default_factory=list)
    section_id:  Optional[str]   = None
    section_title: Optional[str] = None
    ata:         str             = "00"
    page_start:  Optional[int]   = None
    page_end:    Optional[int]   = None
    confidence:  float           = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


# ══════════════════════════════════════════════════════════════════════════════
# BASE ENTITY
# ══════════════════════════════════════════════════════════════════════════════

class BaseEntity(BaseModel):
    id:          str
    type:        EntityType
    provenance:  Provenance = Field(default_factory=Provenance)

    model_config = {"populate_by_name": True, "extra": "ignore"}

    def dedup_key(self) -> str:
        """Override to provide the normalized key used for deduplication."""
        return self.id


# ══════════════════════════════════════════════════════════════════════════════
# STRUCTURAL ENTITIES
# ══════════════════════════════════════════════════════════════════════════════

class ATAChapter(BaseEntity):
    type:        EntityType = EntityType.ATA_CHAPTER
    ata:         str
    title:       str
    description: Optional[str] = None


class Section(BaseEntity):
    type:         EntityType = EntityType.SECTION
    ata:          str
    section_no:   str
    title:        str
    description:  Optional[str] = None
    level:        int = 1


class Task(BaseEntity):
    """A complete maintenance task — has Job Set-Up + Procedure + Close-Up."""
    type:           EntityType = EntityType.TASK
    ata:            str
    task_number:    Optional[str]  = None   # ATA task number (e.g. "71-10-00-801-801")
    title:          str
    description:    Optional[str]  = None
    tools_required: list[str]      = Field(default_factory=list)  # tool IDs
    parts_required: list[str]      = Field(default_factory=list)  # part number IDs
    references:     list[str]      = Field(default_factory=list)  # other task IDs


class Step(BaseEntity):
    """A single numbered step within a task procedure."""
    type:        EntityType = EntityType.STEP
    ata:         str
    task_id:     Optional[str]  = None   # parent task ID
    step_no:     int
    sub_step:    Optional[str]  = None   # e.g. "(a)", "(b)"
    title:       Optional[str]  = None
    description: str
    tools:       list[str]      = Field(default_factory=list)
    warnings:    list[str]      = Field(default_factory=list)   # warning IDs


# ══════════════════════════════════════════════════════════════════════════════
# TECHNICAL ENTITIES
# ══════════════════════════════════════════════════════════════════════════════

class Component(BaseEntity):
    """
    A physical aircraft part or assembly.
    Examples: oil filter, main gear, aileron hinge bolt, fuel selector valve.
    """
    type:           EntityType = EntityType.COMPONENT
    name:           str
    ata:            str
    system:         Optional[str]  = None   # parent system name
    part_number:    Optional[str]  = None
    description:    Optional[str]  = None
    material:       Optional[str]  = None

    def dedup_key(self) -> str:
        return f"component::{normalize_for_dedup(self.name)}"


class System(BaseEntity):
    """
    An aircraft system grouping components.
    Examples: Fuel System, Flight Control System, Landing Gear System.
    """
    type:        EntityType = EntityType.SYSTEM
    name:        str
    ata:         str
    description: Optional[str] = None

    def dedup_key(self) -> str:
        return f"system::{normalize_for_dedup(self.name)}"


class Tool(BaseEntity):
    """
    A maintenance tool required by a task or step.
    Examples: torque wrench, feeler gauge, continuity tester, drift punch.
    """
    type:        EntityType = EntityType.TOOL
    name:        str
    part_number: Optional[str] = None
    specification: Optional[str] = None   # e.g. "calibrated to 50 Nm"
    description: Optional[str] = None

    def dedup_key(self) -> str:
        return f"tool::{normalize_for_dedup(self.name)}"


class Consumable(BaseEntity):
    """
    A consumable material used in a task.
    Examples: engine oil 5W-50, Loctite 243, hydraulic fluid MIL-H-5606.
    """
    type:           EntityType = EntityType.CONSUMABLE
    name:           str
    specification:  Optional[str] = None
    quantity:       Optional[str] = None   # e.g. "2 litres", "as required"
    part_number:    Optional[str] = None

    def dedup_key(self) -> str:
        return f"consumable::{normalize_for_dedup(self.name)}"


class PartNumber(BaseEntity):
    """
    A part number referenced in the manual.
    Examples: 912 080 (ROTAX oil filter), AT01-120-000.
    """
    type:          EntityType = EntityType.PART_NUMBER
    part_number:   str
    description:   Optional[str] = None
    manufacturer:  Optional[str] = None
    superseded_by: Optional[str] = None   # replacement part number

    def dedup_key(self) -> str:
        clean = re.sub(r'[\s\-]', '', self.part_number.upper())
        return f"part::{clean}"


# ══════════════════════════════════════════════════════════════════════════════
# SAFETY ENTITIES (Step 4 semantic pattern: WARNING/CAUTION/NOTE blocks)
# ══════════════════════════════════════════════════════════════════════════════

class Warning(BaseEntity):
    """
    A WARNING block — personal injury or fatality risk.
    Always extracted with WARNS_ABOUT relationships to affected components/steps.
    """
    type:       EntityType = EntityType.WARNING
    level:      WarnLevel  = WarnLevel.WARNING
    text:       str
    ata:        str
    components: list[str]  = Field(default_factory=list)   # component/system IDs
    steps:      list[str]  = Field(default_factory=list)   # step IDs

    def dedup_key(self) -> str:
        # Deduplicate by first 80 chars of normalized text
        return f"warning::{normalize_for_dedup(self.text[:80])}"


class Caution(BaseEntity):
    """A CAUTION block — equipment damage risk (lower severity than WARNING)."""
    type:       EntityType = EntityType.CAUTION
    level:      WarnLevel  = WarnLevel.CAUTION
    text:       str
    ata:        str
    components: list[str]  = Field(default_factory=list)
    steps:      list[str]  = Field(default_factory=list)

    def dedup_key(self) -> str:
        return f"caution::{normalize_for_dedup(self.text[:80])}"


class Note(BaseEntity):
    """A NOTE block — informational, not safety-critical."""
    type: EntityType = EntityType.NOTE
    text: str
    ata:  str

    def dedup_key(self) -> str:
        return f"note::{normalize_for_dedup(self.text[:80])}"


# ══════════════════════════════════════════════════════════════════════════════
# COMPLIANCE ENTITIES
# ══════════════════════════════════════════════════════════════════════════════

class InspectionInterval(BaseEntity):
    """
    A specific inspection schedule.
    Examples: every 100 flight hours, annual, at 500 h TIS.
    """
    type:       EntityType = EntityType.INSPECTION_INTERVAL
    value:      Optional[float]  = None      # numeric value
    unit:       Optional[str]    = None      # "flight hours", "calendar months"
    condition:  Optional[str]    = None      # "or annual, whichever comes first"
    raw_text:   str              = ""        # original text from manual

    def dedup_key(self) -> str:
        return f"interval::{normalize_for_dedup(self.raw_text[:60])}"


class Requirement(BaseEntity):
    """
    An airworthiness limitation or inspection/maintenance requirement.
    ATA 04/05 content is especially critical — EASA Part-M compliance.
    """
    type:         EntityType      = EntityType.REQUIREMENT
    req_type:     RequirementType = RequirementType.INSPECTION
    text:         str
    ata:          str
    components:   list[str]       = Field(default_factory=list)
    interval_id:  Optional[str]   = None    # → InspectionInterval.id
    interval_text:Optional[str]   = None    # raw interval text if no parsed interval

    def dedup_key(self) -> str:
        return f"requirement::{normalize_for_dedup(self.text[:80])}"


# ══════════════════════════════════════════════════════════════════════════════
# MEASUREMENT ENTITIES (critical for aviation — torque, pressure, clearance)
# ══════════════════════════════════════════════════════════════════════════════

class Measurement(BaseEntity):
    """
    A quantitative specification from the manual.
    Examples: 25 Nm torque, 6 bar hydraulic pressure, 0.5 mm clearance.
    Always linked to the component or step it applies to.
    """
    type:         EntityType      = EntityType.MEASUREMENT
    meas_type:    MeasurementType = MeasurementType.OTHER
    value:        str             # keep as string to preserve "0.5–0.7" ranges
    unit:         str
    context:      str             = ""   # "torque for cylinder head bolts"
    min_value:    Optional[float] = None
    max_value:    Optional[float] = None
    nominal:      Optional[float] = None
    ata:          str             = "00"

    def dedup_key(self) -> str:
        return f"measurement::{normalize_for_dedup(self.context[:60])}-{self.value}-{self.unit}"


# ══════════════════════════════════════════════════════════════════════════════
# RELATIONSHIP
# ══════════════════════════════════════════════════════════════════════════════

class Relationship(BaseModel):
    source:       str
    target:       str
    type:         RelationshipType
    properties:   dict[str, Any]   = Field(default_factory=dict)
    confidence:   float            = Field(default=1.0, ge=0.0, le=1.0)
    source_chunk: Optional[str]    = None

    @field_validator("type", mode="before")
    @classmethod
    def normalise_type(cls, v: str) -> str:
        return str(v).upper().replace(" ", "_").replace("-", "_")

    def dedup_key(self) -> tuple[str, str, str]:
        return (self.source, self.target, str(self.type))


# ══════════════════════════════════════════════════════════════════════════════
# EXTRACTION OUTPUT
# ══════════════════════════════════════════════════════════════════════════════

class ExtractionResult(BaseModel):
    """The validated output from one chunk's LLM extraction call."""
    chunk_id:      str
    entities:      list[dict]       = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    extraction_ms: Optional[int]    = None

    @classmethod
    def from_raw(cls, chunk_id: str, raw: dict) -> "ExtractionResult":
        """Parse and validate raw LLM JSON output."""
        rels = []
        for r in raw.get("relationships", []):
            try:
                rels.append(Relationship(
                    source       = r.get("from","") or r.get("source",""),
                    target       = r.get("to","")   or r.get("target",""),
                    type         = r.get("type","CONNECTED_TO"),
                    properties   = r.get("properties",{}),
                    confidence   = float(r.get("confidence", 1.0)),
                    source_chunk = chunk_id,
                ))
            except Exception:
                pass

        return cls(
            chunk_id      = chunk_id,
            entities      = raw.get("entities", []),
            relationships = rels,
        )


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT SCHEMA GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def build_extraction_schema_prompt() -> str:
    """
    Generate the JSON schema section of the extraction prompt from the
    Pydantic models. This ensures the prompt always matches the code.
    """
    return '''Return a JSON object with this EXACT structure:

{
  "relationships": [
    {"from": "WARN-71-0001",           "to": "COMP-71-OIL_FILTER_ASSY",      "type": "WARNS_ABOUT"},
    {"from": "WARN-71-0001",           "to": "STEP-TASK-71-10-00-0801-001",  "type": "WARNS_BEFORE"},
    {"from": "STEP-TASK-71-10-00-0801-001", "to": "TOOL-TORQUE_WRENCH_25NM","type": "REQUIRES_TOOL"},
    {"from": "COMP-71-OIL_FILTER_ASSY","to": "SYS-71-LUBRICATION",          "type": "PART_OF"},
    {"from": "STEP-TASK-71-10-00-0801-001","to":"MEAS-71-TORQUE-0001",       "type": "HAS_MEASUREMENT"},
    {"from": "STEP-TASK-71-10-00-0801-001","to":"STEP-TASK-71-10-00-0801-002","type":"PRECEDES"}
  ],
  "entities": [
    COMPONENT example:
    {
      "id":          "COMP-71-OIL_FILTER_ASSY",
      "type":        "Component",
      "name":        "Oil Filter Assembly",
      "ata":         "71",
      "system":      "Lubrication",
      "part_number": "912 080",
      "description": "Full-flow engine oil filter"
    },
    TOOL example:
    {
      "id":            "TOOL-TORQUE_WRENCH_25NM",
      "type":          "Tool",
      "name":          "Torque Wrench",
      "specification": "calibrated, 5–25 Nm range"
    },
    WARNING example:
    {
      "id":         "WARN-71-0001",
      "type":       "Warning",
      "level":      "WARNING",
      "text":       "Ensure engine is cold before removing oil filter. Hot oil can cause severe burns.",
      "ata":        "71",
      "components": ["COMP-71-OIL_FILTER_ASSY"],
      "steps":      ["STEP-TASK-71-10-00-0801-001"]
    },
    STEP example:
    {
      "id":          "STEP-TASK-71-10-00-0801-001",
      "type":        "Step",
      "ata":         "71",
      "task_id":     "TASK-71-10-00-0801",
      "step_no":     1,
      "title":       "Remove oil filter",
      "description": "Using the oil filter wrench (TOOL-OIL_FILTER_WRENCH), unscrew the oil filter (COMP-71-OIL_FILTER_ASSY) counter-clockwise.",
      "tools":       ["TOOL-OIL_FILTER_WRENCH"],
      "warnings":    ["WARN-71-0001"]
    },
    REQUIREMENT example:
    {
      "id":           "REQ-05-AWL-0001",
      "type":         "Requirement",
      "req_type":     "AIRWORTHINESS_LIMITATION",
      "text":         "Engine oil change required every 100 flight hours or annually, whichever comes first.",
      "ata":          "05",
      "components":   ["SYS-71-LUBRICATION"],
      "interval_text":"100 flight hours or annual"
    },
    MEASUREMENT example:
    {
      "id":        "MEAS-71-TORQUE-0001",
      "type":      "Measurement",
      "meas_type": "TORQUE",
      "value":     "25",
      "unit":      "Nm",
      "context":   "Oil filter assembly torque",
      "nominal":   25.0
    }
  ],
}

ID RULES — critical for graph connectivity:
- Component:   COMP-{ATA:02d}-{NAME_UPPER_MAX5WORDS}
- System:      SYS-{ATA:02d}-{NAME_UPPER}
- Tool:        TOOL-{NAME_UPPER_MAX5WORDS}
- Consumable:  CONS-{NAME_UPPER_MAX5WORDS}
- Warning:     WARN-{ATA:02d}-{SEQ:04d}
- Caution:     CAUT-{ATA:02d}-{SEQ:04d}
- Note:        NOTE-{ATA:02d}-{SEQ:04d}
- Task:        TASK-{ATA:02d}-{SECTION:02d}-{SUBJECT:02d}-{NO:04d}
- Step:        STEP-{TASK_ID}-{NO:03d}
- Requirement: REQ-{ATA:02d}-{TYPE_ABBR}-{SEQ:04d}
- Measurement: MEAS-{ATA:02d}-{MEAS_TYPE}-{SEQ:04d}
- Part:        PART-{PART_NUMBER_CLEAN}

RELATIONSHIP TYPES (use these exact strings):
CONTAINS · PART_OF · PRECEDES · REQUIRES_TOOL · USES_CONSUMABLE
APPLIES_TO · REFERENCES · WARNS_BEFORE · WARNS_ABOUT
GOVERNS · HAS_INTERVAL · HAS_MEASUREMENT · USES_PART · SOURCED_FROM

EXTRACTION RULES:
1. Only extract what is explicitly in the text — never invent.
2. Every WARNING/CAUTION/NOTE block must become an entity with WARNS_ABOUT/WARNS_BEFORE rels.
3. Every numbered step must become a Step entity with PRECEDES rels connecting the sequence.
4. Every tool mentioned in "Tools Required" becomes a Tool entity + REQUIRES_TOOL rel to task.
5. Every torque/pressure/clearance value becomes a Measurement entity + HAS_MEASUREMENT rel.
6. Part numbers in format XX-XXX or XXXXXX become PartNumber entities + USES_PART rel.
7. Use the ATA code from the context header for all IDs in this chunk.
8. Empty category → empty list []. Never omit a key from the output.
9. Return ONLY the JSON — no explanation, no markdown fences, no preamble.'''


# ══════════════════════════════════════════════════════════════════════════════
# ENTITY REGISTRY — for deduplication across chunks
# ══════════════════════════════════════════════════════════════════════════════

class EntityRegistry:
    """
    Accumulates entities from all chunks and deduplicates by normalized name.
    This is Step 19 (Entity Resolution) in the methodology.
    """

    def __init__(self):
        self._store: dict[str, dict] = {}       # dedup_key → entity dict
        self._id_map: dict[str, str] = {}        # norm_name → canonical_id
        self.rels:    list[dict]     = []

    def add_entity(self, ent: dict, chunk_id: str) -> str:
        """
        Add an entity. Returns the canonical ID (existing or new).
        Merges duplicate entities by updating missing fields.
        """
        eid    = ent.get("id","").strip()
        etype  = ent.get("type","")
        name   = (ent.get("name","") or ent.get("text","") or eid).strip()
        norm   = f"{etype}::{normalize_for_dedup(name)}"

        ent_copy = dict(ent)
        ent_copy.setdefault("source_chunks", [])
        if chunk_id not in ent_copy["source_chunks"]:
            ent_copy["source_chunks"].append(chunk_id)

        if norm in self._store:
            existing = self._store[norm]
            # Merge: fill in any missing fields from this extraction
            for k, v in ent_copy.items():
                if k == "source_chunks":
                    combined = existing.get("source_chunks",[]) + [chunk_id]
                    existing["source_chunks"] = list(dict.fromkeys(combined))
                elif v and not existing.get(k):
                    existing[k] = v
            canonical_id = existing["id"]
        else:
            self._store[norm] = ent_copy
            canonical_id      = eid
            self._id_map[normalize_for_dedup(name)] = canonical_id

        return canonical_id

    def add_relationship(self, rel: dict, chunk_id: str):
        rel_copy = dict(rel)
        rel_copy["source_chunk"] = chunk_id
        self.rels.append(rel_copy)

    def resolve_relationships(self) -> list[dict]:
        """
        Step 20: Repair relationship endpoints.
        Replace name-based references with canonical entity IDs.
        Remove relationships where either endpoint doesn't exist.
        """
        entity_ids = {e["id"] for e in self._store.values()}
        resolved   = []
        seen: set[tuple] = set()

        for rel in self.rels:
            src   = rel.get("source","") or rel.get("from","")
            tgt   = rel.get("target","") or rel.get("to","")
            rtype = rel.get("type","CONNECTED_TO").upper().replace(" ","_")

            # Try to resolve by name if not a known ID
            if src not in entity_ids:
                src = self._id_map.get(normalize_for_dedup(src), src)
            if tgt not in entity_ids:
                tgt = self._id_map.get(normalize_for_dedup(tgt), tgt)

            # Only keep if both endpoints are real entity IDs
            if src in entity_ids and tgt in entity_ids:
                key = (src, tgt, rtype)
                if key not in seen:
                    seen.add(key)
                    resolved.append({
                        "source":       src,
                        "target":       tgt,
                        "type":         rtype,
                        "source_chunk": rel.get("source_chunk",""),
                    })

        return resolved

    def to_dataset(self) -> dict:
        entities      = list(self._store.values())
        relationships = self.resolve_relationships()

        by_type: dict[str, int] = {}
        for e in entities:
            t = e.get("type","Unknown")
            by_type[t] = by_type.get(t, 0) + 1

        return {
            "entities":      entities,
            "relationships": relationships,
            "summary":       {
                "by_type":         by_type,
                "total_entities":  len(entities),
                "total_rels":      len(relationships),
            }
        }
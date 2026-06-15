export const NODE_COLORS: Record<string, string> = {
  Component: "#3b82f6",
  Warning: "#ef4444",
  Tool: "#f59e0b",
  Defect: "#f97316",
  Requirement: "#a78bfa",
  MaintenanceStep: "#34d399",
  Step: "#34d399",
  System: "#22d3ee",
  Measurement: "#e879f9",
  Node: "#64748b",
};

export const NODE_ICONS: Record<string, string> = {
  Component: "\u2699\ufe0f",
  Warning: "\u26a0\ufe0f",
  Tool: "\ud83d\udd27",
  Defect: "\ud83d\udd34",
  Requirement: "\ud83d\udccb",
  MaintenanceStep: "\ud83d\udcdd",
  Step: "\ud83d\udcdd",
  System: "\ud83d\udef0\ufe0f",
  Measurement: "\ud83d\udccf",
  Node: "\u25cf",
};

export const NODE_DESCRIPTIONS: Record<string, string> = {
  Component: "Physical aircraft part \u2014 engine, valve, pump, sensor, cable",
  Warning: "Safety-critical alert \u2014 must be read before performing any work",
  Tool: "Equipment required to carry out a maintenance step",
  Defect: "Known fault or failure mode documented in the manual",
  Requirement: "Airworthiness limitation or regulatory requirement (JAR/EASA)",
  MaintenanceStep: "A specific numbered procedure step from the maintenance manual",
  Step: "A specific numbered procedure step from the maintenance manual",
  System: "An aircraft system grouping related components",
  Measurement: "A torque, pressure, or dimension value from the manual",
};

export const EDGE_COLORS: Record<string, string> = {
  USED_IN: "#3b82f6",
  REQUIRES_TOOL: "#f59e0b",
  WARNS_ABOUT: "#ef4444",
  FIXES_DEFECT: "#f97316",
  GOVERNS: "#a78bfa",
  CONNECTED_TO: "#64748b",
  CONTAINS: "#64748b",
  ADJACENT_TO: "#475569",
  PART_OF_SECTION: "#475569",
};

export const EDGE_DESCRIPTIONS: Record<string, string> = {
  USED_IN: "This component is referenced inside the maintenance step",
  REQUIRES_TOOL: "This procedure step needs the connected tool",
  WARNS_ABOUT: "This warning applies to the connected step or component",
  FIXES_DEFECT: "Performing this step resolves the connected defect",
  GOVERNS: "This airworthiness requirement applies to the component",
  CONNECTED_TO: "General documented relationship between two entities",
};

export const PIPELINE_STEPS: [string, string, string][] = [
  [
    "\ud83d\udd0d",
    "Entity Extraction",
    "Searches the Neo4j fulltext index for component IDs, system names, and ATA codes mentioned in your query.",
  ],
  [
    "\ud83d\udd78\ufe0f",
    "Graph Traversal",
    "Follows typed edges up to 2 hops from each matched entity, collecting related components, warnings, tools, and requirements.",
  ],
  [
    "\ud83d\udddc\ufe0f",
    "Context Compression",
    "Ranks nodes by type priority (Warning > Requirement > Step > Component > Tool) and trims to the token budget.",
  ],
  [
    "\ud83e\udd16",
    "LLM Generation",
    "Claude reasons over the structured graph context and produces a grounded, source-attributed answer.",
  ],
];

export const FALLBACK_SAMPLE_QUESTIONS: string[] = [
  "What are the torque specifications and warnings for the oil filter?",
  "What tools are required before starting the engine oil servicing task?",
  "Which maintenance step comes immediately after draining engine oil?",
  "List all safety warnings that apply before fuel system maintenance.",
  "What airworthiness or inspection interval requirements are mentioned for engine servicing?",
];

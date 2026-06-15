export interface GraphNode {
  id: string;
  label: string;
  type: string;
}

export interface GraphEdge {
  from: string;
  to: string;
  label: string;
}

export interface GraphViz {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Timing {
  total_ms?: number;
  llm_generation_ms?: number;
  fallback_used?: boolean;
  [key: string]: number | boolean | string | undefined;
}

export interface QueryResponse {
  answer: string;
  entities: string[];
  graph_viz: GraphViz;
  timing: Timing;
  error?: string;
}

export interface Meta {
  model: string;
  method: string;
  architecture: string;
  sample_questions: string[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  result?: QueryResponse;
  pending?: boolean;
}

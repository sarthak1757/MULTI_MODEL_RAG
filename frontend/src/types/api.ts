export type SourceStatus = "uploaded" | "processing" | "ready" | "failed";
export type SourceType = "video" | "pdf" | "image";

export interface Source {
  id: string;
  source_id?: string;
  filename: string;
  source_type: SourceType;
  duration: number | null;
  status: SourceStatus;
  error_message?: string | null;
  created_at: string;
}

export interface ProcessResult {
  source_id: string;
  status: SourceStatus;
  stats: Record<string, number | GraphSyncStatus>;
  error?: string;
}

export type GraphStatus = "ready" | "not_synced" | "skipped" | "failed";

export interface GraphSyncStatus {
  enabled: boolean;
  status: GraphStatus;
  error?: string;
}

export interface GraphNode {
  id: string;
  label: "Source" | "Event" | "Observation" | "Entity";
  properties: Record<string, unknown>;
}

export interface GraphRelationship {
  id: string;
  source_node_id: string;
  target_node_id: string;
  relation: string;
  properties: Record<string, unknown>;
}

export interface SourceGraph {
  source: Record<string, unknown>;
  nodes: GraphNode[];
  relationships: GraphRelationship[];
}

export interface SourceGraphResponse extends GraphSyncStatus {
  graph: SourceGraph | null;
}

export interface EvidenceFrame {
  observation_id: string;
  timestamp: number | null;
}

export interface EvidenceOcr {
  timestamp: number | null;
  text: string;
  confidence: number | null;
}

export interface EvidenceEvent {
  event_id: string;
  title: string;
  start_time: number | null;
  end_time: number | null;
  score: number;
  transcript: string;
  ocr: EvidenceOcr[];
  entities: string[];
  frames: EvidenceFrame[];
}

export interface QueryResponse {
  answer: string;
  confidence: number;
  used_modalities: string[];
  citations: unknown[];
  error: string | null;
  evidence: EvidenceEvent[];
}

export interface TimelineEvent {
  id: string;
  title: string;
  summary: string;
  start_time: number | null;
  end_time: number | null;
  confidence: number | null;
  modalities: string[];
  entities: string[];
}

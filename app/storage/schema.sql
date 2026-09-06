CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (
        source_type IN ('video', 'pdf', 'image')
    ),
    path TEXT NOT NULL,
    duration REAL,
    status TEXT NOT NULL CHECK (
        status IN ('uploaded', 'processing', 'ready', 'failed')
    ),
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sources_status
    ON sources (status);

CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    modality TEXT NOT NULL CHECK (
        modality IN ('transcript', 'frame', 'ocr', 'vision', 'image', 'document')
    ),
    content TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    start_time REAL,
    end_time REAL,
    timestamp REAL,
    confidence REAL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observations_source_id
    ON observations (source_id);

CREATE INDEX IF NOT EXISTS idx_observations_time
    ON observations (source_id, start_time, end_time, timestamp);

CREATE TABLE IF NOT EXISTS semantic_events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_id TEXT NOT NULL,
    start_time REAL,
    end_time REAL,
    entities TEXT NOT NULL DEFAULT '[]',
    confidence REAL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_semantic_events_source_id
    ON semantic_events (source_id);

CREATE INDEX IF NOT EXISTS idx_semantic_events_time
    ON semantic_events (source_id, start_time, end_time);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    entity_type TEXT,
    confidence REAL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_normalized_name_unique
    ON entities (normalized_name);

CREATE TABLE IF NOT EXISTS event_entities (
    event_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    confidence REAL,
    PRIMARY KEY (event_id, entity_id),
    FOREIGN KEY (event_id) REFERENCES semantic_events (id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id) REFERENCES entities (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_event_entities_event_id
    ON event_entities (event_id);

CREATE INDEX IF NOT EXISTS idx_event_entities_entity_id
    ON event_entities (entity_id);

CREATE TABLE IF NOT EXISTS event_observations (
    event_id TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, observation_id),
    FOREIGN KEY (event_id) REFERENCES semantic_events (id) ON DELETE CASCADE,
    FOREIGN KEY (observation_id) REFERENCES observations (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_event_observations_event_id
    ON event_observations (event_id);

CREATE INDEX IF NOT EXISTS idx_event_observations_observation_id
    ON event_observations (observation_id);

CREATE TABLE IF NOT EXISTS evidence_edges (
    id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    confidence REAL,
    method TEXT NOT NULL CHECK (
        method IN ('temporal', 'provenance', 'entity_match', 'embedding', 'llm')
    ),
    evidence_observation_ids TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_edges_source_node
    ON evidence_edges (source_node_id);

CREATE INDEX IF NOT EXISTS idx_evidence_edges_target_node
    ON evidence_edges (target_node_id);

CREATE INDEX IF NOT EXISTS idx_evidence_edges_method
    ON evidence_edges (method);

CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_edges_unique_relation
    ON evidence_edges (source_node_id, target_node_id, relation, method);

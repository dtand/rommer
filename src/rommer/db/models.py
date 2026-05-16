"""SQLite schema definitions."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS project (
    id INTEGER PRIMARY KEY,
    game_id TEXT NOT NULL UNIQUE,
    game_title TEXT
);

CREATE TABLE IF NOT EXISTS section (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES project(id),
    section_id TEXT NOT NULL,
    title TEXT,
    type TEXT,
    line_start INTEGER,
    line_end INTEGER,
    description TEXT,
    parent_section_id TEXT
);

CREATE TABLE IF NOT EXISTS game_system (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES project(id),
    name TEXT NOT NULL,
    description TEXT,
    table_names TEXT
);

CREATE TABLE IF NOT EXISTS control_mapping (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES project(id),
    context TEXT,
    button TEXT,
    action TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS schema_sql (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES project(id),
    sql_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_data_table (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES project(id),
    table_name TEXT NOT NULL,
    column_names TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_data_row (
    id INTEGER PRIMARY KEY,
    table_id INTEGER REFERENCES game_data_table(id),
    row_index INTEGER,
    row_data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS walkthrough_resource (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES project(id),
    type TEXT,
    section_ref TEXT,
    content TEXT,
    line_start INTEGER,
    line_end INTEGER
);

CREATE TABLE IF NOT EXISTS graph_node (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES project(id),
    node_id TEXT NOT NULL,
    name TEXT,
    title TEXT,
    description TEXT,
    section_ref TEXT,
    goal TEXT,
    success_criteria TEXT,
    order_index INTEGER,
    action_type TEXT,
    version_specific TEXT,
    estimated_inputs TEXT,
    discovery_hints TEXT,
    human_hints TEXT,
    status TEXT DEFAULT 'pending',
    tags TEXT
);
CREATE INDEX IF NOT EXISTS idx_node_section ON graph_node(section_ref);
CREATE INDEX IF NOT EXISTS idx_node_order ON graph_node(order_index);

CREATE TABLE IF NOT EXISTS graph_edge (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES project(id),
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    edge_type TEXT
);
CREATE INDEX IF NOT EXISTS idx_edge_from ON graph_edge(from_node);
CREATE INDEX IF NOT EXISTS idx_edge_to ON graph_edge(to_node);

CREATE TABLE IF NOT EXISTS discovery (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES project(id),
    label TEXT NOT NULL,
    address TEXT NOT NULL,
    data_type TEXT,
    memory_domain TEXT DEFAULT 'EWRAM',
    confidence TEXT DEFAULT 'confirmed',
    discovered_by_node TEXT,
    discovery_method TEXT,
    verified_by TEXT DEFAULT 'agent',
    schema_target TEXT,
    notes TEXT,
    tier TEXT DEFAULT 'scratch',
    promotion_reason TEXT,
    source TEXT DEFAULT 'dynamic',
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_discovery_node ON discovery(discovered_by_node);
CREATE INDEX IF NOT EXISTS idx_discovery_label ON discovery(label);
CREATE INDEX IF NOT EXISTS idx_discovery_tier ON discovery(tier);

CREATE TABLE IF NOT EXISTS execution_run (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES project(id),
    node_id TEXT NOT NULL,
    run_number INTEGER DEFAULT 1,
    status TEXT DEFAULT 'in_progress',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    wall_time_seconds REAL,
    frames_used INTEGER,
    error TEXT,
    plan_json TEXT,
    result_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_node ON execution_run(node_id);

CREATE TABLE IF NOT EXISTS node_candidate (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES project(id),
    node_id TEXT NOT NULL,
    run_id INTEGER REFERENCES execution_run(id),
    label TEXT,
    address TEXT NOT NULL,
    data_type TEXT,
    before_value TEXT,
    after_value TEXT,
    confidence TEXT DEFAULT 'volatile',
    method TEXT,
    schema_target TEXT,
    reasoning TEXT,
    evidence_paths TEXT,
    review_status TEXT DEFAULT 'pending',
    reviewed_at TIMESTAMP,
    rejection_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_candidate_node ON node_candidate(node_id);
CREATE INDEX IF NOT EXISTS idx_candidate_review ON node_candidate(review_status);

-- Knowledge resource tracking
CREATE TABLE IF NOT EXISTS knowledge_resource (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES project(id),
    type TEXT NOT NULL,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    description TEXT,
    metadata TEXT
);

-- Knowledge linked to nodes
CREATE TABLE IF NOT EXISTS node_knowledge (
    id INTEGER PRIMARY KEY,
    node_id TEXT NOT NULL,
    resource_id INTEGER REFERENCES knowledge_resource(id),
    relevance TEXT,
    context_snippet TEXT
);

-- Job tracking
CREATE TABLE IF NOT EXISTS job (
    id TEXT PRIMARY KEY,
    project_id INTEGER REFERENCES project(id),
    type TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    progress TEXT,
    config TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_job_project ON job(project_id);
CREATE INDEX IF NOT EXISTS idx_job_status ON job(status);

CREATE TABLE IF NOT EXISTS job_event (
    id INTEGER PRIMARY KEY,
    job_id TEXT REFERENCES job(id),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    type TEXT NOT NULL,
    data TEXT
);
CREATE INDEX IF NOT EXISTS idx_job_event_job ON job_event(job_id);

-- Staging table for parallel job discoveries (merged after all complete)
CREATE TABLE IF NOT EXISTS job_discovery (
    id INTEGER PRIMARY KEY,
    job_id TEXT REFERENCES job(id),
    label TEXT NOT NULL,
    address TEXT NOT NULL,
    data_type TEXT,
    confidence TEXT DEFAULT 'probable',
    notes TEXT,
    metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_job_discovery_job ON job_discovery(job_id);
"""


def init_db(conn):
    """Create all tables."""
    conn.executescript(SCHEMA_SQL)

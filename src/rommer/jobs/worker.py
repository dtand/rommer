"""Job worker functions - executed in background threads."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rommer.config import Project
    from rommer.jobs.manager import JobManager


def run_graph_gen(manager: JobManager, job_id: str, project: Project, config: dict):
    """Run graph generation (pass 4 + pass 5) with streaming logs."""
    from rommer.preprocessor.pass5_augment import augment_nodes
    from rommer.preprocessor.pass4_graph import generate_graph_streaming

    model = config.get("model", "opus")
    walkthrough = config.get("walkthrough")

    # Find walkthrough file
    guides_dir = project.knowledge_dir / "guides"
    if walkthrough:
        wt_path = guides_dir / walkthrough
    else:
        wt_files = list(guides_dir.glob("walkthrough*")) if guides_dir.exists() else []
        if not wt_files:
            raise FileNotFoundError("No walkthrough file found")
        wt_path = wt_files[0]

    # Load prior results
    output_dir = project.graph_dir / "preprocessor_output"
    section_map = _load_json(output_dir / "pass1_section_map.json")
    systems = _load_json(output_dir / "pass2_systems.json")
    data = _load_json(output_dir / "pass3_data.json")

    # Pass 4: Graph generation with streaming
    manager.emit_progress(job_id, "Pass 4: Graph Generation", 10, "Starting graph generation...")
    _emit_log(manager, job_id, f"Using walkthrough: {wt_path.name}")
    _emit_log(manager, job_id, f"Model: {model}")
    _emit_log(manager, job_id, f"Sections: {len(section_map.get('sections', []))}")

    def on_event(event: dict):
        """Stream callback — log agent activity."""
        etype = event.get("type", "")
        if etype == "agent_text":
            text = event.get("text", "").strip()
            if text and len(text) > 5:
                # Only log meaningful text chunks
                _emit_log(manager, job_id, text[:200])
        elif etype == "agent_tool_call":
            tool = event.get("tool", "")
            _emit_log(manager, job_id, f"[tool] {tool}")

    graph = generate_graph_streaming(model, wt_path, section_map, systems, data, on_event=on_event)
    (output_dir / "pass4_graph.json").write_text(json.dumps(graph, indent=2))

    node_count = len(graph.get("nodes", []))
    edge_count = len(graph.get("edges", []))
    _emit_log(manager, job_id, f"Generated {node_count} nodes, {edge_count} edges")

    # Store in DB
    manager.emit_progress(job_id, "Storing graph", 70, f"{node_count} nodes, {edge_count} edges")
    _store_graph(project, graph)

    # Pass 5: Augmentation
    manager.emit_progress(job_id, "Pass 5: Augmentation", 85, "Tagging nodes + linking knowledge...")
    augment_result = augment_nodes(project, model)
    (output_dir / "pass5_augment.json").write_text(json.dumps(augment_result, indent=2))
    _emit_log(manager, job_id, f"Tagged {augment_result.get('tagged_count', 0)} nodes, linked {augment_result.get('links_created', 0)} resources")

    manager.complete_job(job_id, f"Generated {node_count} nodes")


def _emit_log(manager: JobManager, job_id: str, message: str):
    """Emit a log event for a job."""
    import json as _json
    manager.db.execute(
        "INSERT INTO job_event (job_id, type, data) VALUES (?, 'log', ?)",
        (job_id, _json.dumps({"message": message})),
    )
    manager.db.commit()
    from rommer.jobs.manager import _broadcast
    _broadcast({
        "type": "job_log",
        "job_id": job_id,
        "project": manager.project.name,
        "data": {"message": message},
    })


def run_knowledge_analysis(manager: JobManager, job_id: str, project: Project, config: dict):
    """Analyze all knowledge resources using a tool-equipped agent."""
    model = config.get("model", "opus")

    # List files
    knowledge_dir = project.knowledge_dir
    if knowledge_dir.exists():
        files = [f.name for f in knowledge_dir.rglob("*") if f.is_file() and not f.name.startswith(".")]
        _emit_log(manager, job_id, f"Found {len(files)} knowledge files")
        for f in files:
            _emit_log(manager, job_id, f"  {f}")

    # Launch agent with full tool access and streaming
    manager.emit_progress(job_id, "Agent analysis", 20, "Agent analyzing resources...")
    _emit_log(manager, job_id, f"Spawning knowledge analysis agent (model: {model})")

    from rommer.agents.knowledge_analyzer import KnowledgeAnalyzer
    analyzer = KnowledgeAnalyzer(project)

    def on_event(event: dict):
        etype = event.get("type", "")
        if etype == "agent_text":
            text = event.get("text", "").strip()
            if text and len(text) > 3:
                _emit_log(manager, job_id, text[:300])
                manager.emit_progress(job_id, "Agent analysis", 50, text[:100])
        elif etype == "agent_tool_call":
            tool = event.get("tool", "")
            _emit_log(manager, job_id, f"[tool] {tool}")

    result = analyzer.spawn(model=model, timeout=1800, on_event=on_event)

    discoveries = 0
    if result and isinstance(result, dict):
        staged = analyzer.complete(result)
        discoveries = len(staged)
        _emit_log(manager, job_id, f"Agent discovered {discoveries} addresses")

        # Log observations if any
        for obs in result.get("observations", []):
            _emit_log(manager, job_id, f"  {obs}")

    manager.complete_job(job_id, f"Found {discoveries} discoveries")


def run_ghidra_decompile(manager: JobManager, job_id: str, project: Project, config: dict):
    """Run Ghidra decompilation workflow."""
    import subprocess

    manager.emit_progress(job_id, "Exporting labels", 10, "Preparing discovery labels for Ghidra...")

    # Export labels
    from rommer.cli.commands.ghidra_decompile import _export_labels
    _export_labels(project)

    manager.emit_progress(job_id, "Decompiling", 30, "Running Ghidra headless analysis (this may take a while)...")

    # TODO: Actually invoke Ghidra headless
    # For now, mark as needing manual execution
    manager.emit_progress(job_id, "Pending", 50, "Ghidra headless execution not yet automated")
    manager.complete_job(job_id, "Labels exported. Run Ghidra manually for full decompilation.")


def _store_graph(project: Project, graph: dict):
    """Store graph nodes and edges in DB."""
    import json
    conn = project.get_db()
    project_id = conn.execute("SELECT id FROM project LIMIT 1").fetchone()[0]

    # Clear existing
    conn.execute("DELETE FROM graph_node WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM graph_edge WHERE project_id = ?", (project_id,))

    for i, node in enumerate(graph.get("nodes", [])):
        conn.execute(
            """INSERT INTO graph_node
               (project_id, node_id, name, title, description, section_ref,
                goal, success_criteria, order_index, action_type,
                estimated_inputs, discovery_hints, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, node.get("node_id"), node.get("name"), node.get("title"),
             node.get("description"), node.get("section_ref"),
             node.get("goal"), node.get("success_criteria"),
             node.get("order_index", i), node.get("action_type"),
             json.dumps(node.get("estimated_inputs")) if isinstance(node.get("estimated_inputs"), list) else node.get("estimated_inputs"),
             json.dumps(node.get("discovery_hints", [])),
             json.dumps(node.get("tags", []))),
        )

    for edge in graph.get("edges", []):
        from_node = edge.get("from_node") or edge.get("from")
        to_node = edge.get("to_node") or edge.get("to")
        if from_node and to_node:
            conn.execute(
                "INSERT INTO graph_edge (project_id, from_node, to_node, edge_type) VALUES (?, ?, ?, ?)",
                (project_id, from_node, to_node, edge.get("edge_type") or edge.get("type")),
            )

    conn.commit()
    conn.close()


def _load_json(path) -> dict:
    """Load JSON file, return empty dict if missing."""
    if path.exists():
        return json.loads(path.read_text())
    return {}


# Registry of job types to worker functions
WORKERS = {
    "graph_gen": run_graph_gen,
    "knowledge_analysis": run_knowledge_analysis,
    "ghidra_decompile": run_ghidra_decompile,
}

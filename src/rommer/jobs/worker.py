"""Job worker functions - executed in background threads."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rommer.config import Project
    from rommer.jobs.manager import JobManager


def run_graph_gen(manager: JobManager, job_id: str, project: Project, config: dict):
    """Run graph generation (pass 4 + pass 5)."""
    from rommer.preprocessor.pass4_graph import generate_graph
    from rommer.preprocessor.pass5_augment import augment_nodes

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

    # Pass 4: Graph generation
    manager.emit_progress(job_id, "Pass 4: Graph Generation", 20, "Generating node DAG from walkthrough...")
    graph = generate_graph(model, wt_path, section_map, systems, data)
    (output_dir / "pass4_graph.json").write_text(json.dumps(graph, indent=2))

    # Store in DB
    manager.emit_progress(job_id, "Storing graph", 70, f"{len(graph.get('nodes', []))} nodes, {len(graph.get('edges', []))} edges")
    _store_graph(project, graph)

    # Pass 5: Augmentation
    manager.emit_progress(job_id, "Pass 5: Augmentation", 85, "Tagging nodes + linking knowledge...")
    augment_result = augment_nodes(project, model)
    (output_dir / "pass5_augment.json").write_text(json.dumps(augment_result, indent=2))

    node_count = len(graph.get("nodes", []))
    manager.complete_job(job_id, f"Generated {node_count} nodes")


def run_knowledge_analysis(manager: JobManager, job_id: str, project: Project, config: dict):
    """Analyze all knowledge resources for discoveries."""
    manager.emit_progress(job_id, "Scanning resources", 10, "Cataloging knowledge files...")

    # Parse structured codes first (no AI needed)
    from rommer.knowledge.code_parser import parse_project_codes
    codes_found = parse_project_codes(project)
    manager.emit_progress(job_id, "Code parsing", 40, f"Found {codes_found} codes")

    # Agent-driven analysis of remaining resources
    manager.emit_progress(job_id, "Agent analysis", 60, "Analyzing supplementary resources...")
    from rommer.agents.knowledge_analyzer import KnowledgeAnalyzer
    analyzer = KnowledgeAnalyzer(project)
    result = analyzer.spawn(model=config.get("model", "sonnet"))

    discoveries = 0
    if result:
        staged = analyzer.complete(result)
        discoveries = len(staged)

    total = codes_found + discoveries
    manager.complete_job(job_id, f"Found {total} discoveries ({codes_found} from codes, {discoveries} from analysis)")


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

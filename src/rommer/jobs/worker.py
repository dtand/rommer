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

    # Count files for progress tracking
    knowledge_dir = project.knowledge_dir
    file_count = 0
    if knowledge_dir.exists():
        files = [f.name for f in knowledge_dir.rglob("*") if f.is_file() and not f.name.startswith(".")]
        file_count = len(files)
        _emit_log(manager, job_id, f"Found {file_count} knowledge files")
        for f in files:
            _emit_log(manager, job_id, f"  {f}")

    manager.emit_progress(job_id, "Agent analysis", 10, "Spawning agent...")
    _emit_log(manager, job_id, f"Spawning knowledge analysis agent (model: {model}, job: {job_id})")

    from rommer.agents.knowledge_analyzer import KnowledgeAnalyzer
    analyzer = KnowledgeAnalyzer(project)

    # Track progress based on tool calls to files
    files_seen: set[str] = set()

    def on_event(event: dict):
        etype = event.get("type", "")
        if etype == "agent_text":
            text = event.get("text", "").strip()
            if text and len(text) > 3:
                _emit_log(manager, job_id, text[:300])
        elif etype == "agent_tool_call":
            tool = event.get("tool", "")
            tool_input = event.get("input", {})
            _emit_log(manager, job_id, f"[tool] {tool}")
            # Track file access for progress
            if tool == "Read" and isinstance(tool_input, dict):
                file_path = tool_input.get("file_path", "")
                if file_path and "knowledge/" in file_path and file_path not in files_seen:
                    files_seen.add(file_path)
                    if file_count > 0:
                        pct = min(85, 10 + int(75 * len(files_seen) / file_count))
                        fname = file_path.split("/")[-1]
                        manager.emit_progress(job_id, f"Analyzing: {fname}", pct, f"File {len(files_seen)}/{file_count}")

    result = analyzer.spawn(model=model, timeout=1800, on_event=on_event)

    discoveries = 0
    if result and isinstance(result, dict):
        stage = config.get("stage_discoveries", False)
        if stage:
            # Write to staging table for later merge
            discoveries = _stage_discoveries(manager, job_id, result)
            _emit_log(manager, job_id, f"Staged {discoveries} discoveries for merge")
        else:
            # Write directly to discovery table
            staged = analyzer.complete(result)
            discoveries = len(staged)
            _emit_log(manager, job_id, f"Agent discovered {discoveries} addresses")

        for obs in result.get("observations", []):
            _emit_log(manager, job_id, f"  {obs}")

    manager.complete_job(job_id, f"Found {discoveries} discoveries")


def _stage_discoveries(manager: JobManager, job_id: str, result: dict) -> int:
    """Write discoveries to staging table (for parallel merge)."""
    import json as _json
    discoveries = result.get("discoveries", []) or result.get("candidates", [])
    count = 0
    for d in discoveries:
        addr = d.get("address", "")
        label = d.get("label", "")
        if not addr or not label:
            continue
        metadata = d.get("metadata")
        manager.db.execute(
            "INSERT INTO job_discovery (job_id, label, address, data_type, confidence, notes, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, label, addr, d.get("data_type", "u16"),
             d.get("confidence", "probable"), d.get("notes", ""),
             _json.dumps(metadata) if metadata else None),
        )
        count += 1
    manager.db.commit()
    return count


def run_ghidra_decompile(manager: JobManager, job_id: str, project: Project, config: dict):
    """Run full Ghidra decompilation in a single headless call.

    One analyzeHeadless invocation:
    - Import ROM at 0x08000000 (ARM:LE:32:v4t)
    - Add memory regions (IWRAM, EWRAM, etc.) via preScript
    - Auto-analyze
    - Export all decompiled functions via postScript
    """
    import os
    import shutil
    import subprocess

    # Find analyzeHeadless
    ghidra_headless = os.environ.get("GHIDRA_HEADLESS", "/Applications/ghidra_12.0_PUBLIC/support/analyzeHeadless")
    if not os.path.exists(ghidra_headless):
        # Try homebrew path
        ghidra_headless = "/opt/homebrew/Cellar/ghidra/12.0/libexec/support/analyzeHeadless"
    if not os.path.exists(ghidra_headless):
        raise FileNotFoundError(f"analyzeHeadless not found. Set GHIDRA_HEADLESS env var.")

    rom_path = project.rom_path
    if not rom_path.exists():
        raise FileNotFoundError(f"ROM not found: {rom_path}")

    # Scripts directory
    from pathlib import Path
    scripts_dir = Path(__file__).parent.parent / "static_analysis" / "ghidra_scripts"

    # Ghidra project directory (temporary, within project workspace)
    ghidra_project_dir = project.ghidra_dir
    ghidra_project_dir.mkdir(parents=True, exist_ok=True)
    project_name = project.name.replace("-", "_")

    # Export discovery labels for import script
    manager.emit_progress(job_id, "Preparing", 5, "Exporting discovery labels...")
    from rommer.cli.commands.ghidra_decompile import _export_labels
    _export_labels(project)
    _emit_log(manager, job_id, f"ROM: {rom_path}")
    _emit_log(manager, job_id, f"Ghidra project: {ghidra_project_dir}/{project_name}")
    _emit_log(manager, job_id, f"Scripts: {scripts_dir}")

    # Output directory for decompiled code
    output_dir = project.src_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "functions").mkdir(exist_ok=True)

    # Set env var so export script knows where to write
    env = os.environ.copy()
    env["ROMMER_OUTPUT_DIR"] = str(output_dir)

    # Build the command
    cmd = [
        ghidra_headless,
        str(ghidra_project_dir),
        project_name,
        "-import", str(rom_path),
        "-processor", "ARM:LE:32:v4t",
        "-cspec", "default",
        "-loader", "BinaryLoader",
        "-loader-baseAddr", "0x08000000",
        "-preScript", str(scripts_dir / "setup_memory.py"),
        "-postScript", str(scripts_dir / "export_decompiled.py"),
        "-postScript", str(scripts_dir / "export_split.py"),
        "-scriptPath", str(scripts_dir),
        "-max-cpu", "4",
        "-analysisTimeoutPerFile", "600",
        "-overwrite",
    ]

    _emit_log(manager, job_id, f"Command: {' '.join(cmd[:6])}...")
    manager.emit_progress(job_id, "Decompiling", 15, "Running Ghidra headless analysis...")
    _emit_log(manager, job_id, "Starting Ghidra (this typically takes 5-15 minutes)...")

    # Run with streaming output
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    func_count = 0
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue

        # Parse Ghidra output for progress updates
        if "Importing" in line:
            manager.emit_progress(job_id, "Importing ROM", 20, line[:100])
        elif "Analyzing" in line or "analysis" in line.lower():
            manager.emit_progress(job_id, "Analyzing", 40, line[:100])
        elif "Decompiling" in line or "decompiled" in line.lower():
            # Track function count from export script output
            if "decompiled" in line.lower():
                try:
                    # Look for patterns like "1234 decompiled"
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if "decompiled" in p.lower() and i > 0:
                            func_count = int(parts[i - 1].replace(",", ""))
                except (ValueError, IndexError):
                    pass
            pct = min(90, 50 + (func_count // 500))
            manager.emit_progress(job_id, "Decompiling", pct, f"{func_count} functions...")
        elif "Done" in line or "complete" in line.lower():
            manager.emit_progress(job_id, "Finishing", 95, line[:100])

        _emit_log(manager, job_id, line[:200])

    proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(f"Ghidra exited with code {proc.returncode}")

    # Count output files
    functions_dir = output_dir / "functions"
    if functions_dir.exists():
        func_files = list(functions_dir.glob("*.c"))
        func_count = len(func_files) if func_files else func_count

    _emit_log(manager, job_id, f"Decompilation complete: {func_count} functions")
    manager.complete_job(job_id, f"Decompiled {func_count} functions")


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

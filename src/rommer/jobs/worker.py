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
        # Prefer .txt files, then largest file
        txt_files = [f for f in wt_files if f.suffix == ".txt"]
        wt_path = txt_files[0] if txt_files else max(wt_files, key=lambda f: f.stat().st_size)

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


def _emit_log(manager: JobManager, job_id: str, message: str, log_type: str = "log"):
    """Emit a log event for a job — DB only (Postgres NOTIFY handles broadcast)."""
    import json as _json
    placeholder = "%s" if hasattr(manager.db, '_conn') else "?"
    manager.db.execute(
        f"INSERT INTO job_event (job_id, type, data) VALUES ({placeholder}, 'log', {placeholder})",
        (job_id, _json.dumps({"message": message, "log_type": log_type})),
    )
    manager.db.commit()


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
                _emit_log(manager, job_id, text[:500], "log")
        elif etype == "agent_thinking":
            text = event.get("text", "").strip()
            if text and len(text) > 3:
                _emit_log(manager, job_id, text[:500], "thinking")
        elif etype == "agent_tool_call":
            tool = event.get("tool", "")
            tool_input = event.get("input", {})
            detail = ""
            if tool == "Bash":
                detail = f": {tool_input.get('command', '')[:200]}"
            elif tool == "Read":
                detail = f": {tool_input.get('file_path', '')}"
            elif tool in ("Edit", "Write"):
                detail = f": {tool_input.get('file_path', '')}"
            elif tool in ("Grep", "Glob"):
                detail = f": {tool_input.get('pattern', '')}"
            _emit_log(manager, job_id, f"[{tool}]{detail}", "tool_call")
            # Track file access for progress
            if tool == "Read" and isinstance(tool_input, dict):
                file_path = tool_input.get("file_path", "")
                if file_path and "knowledge/" in file_path and file_path not in files_seen:
                    files_seen.add(file_path)
                    if file_count > 0:
                        pct = min(85, 10 + int(75 * len(files_seen) / file_count))
                        fname = file_path.split("/")[-1]
                        manager.emit_progress(job_id, f"Analyzing: {fname}", pct, f"File {len(files_seen)}/{file_count}")
        elif etype == "agent_tool_result":
            output = event.get("output", "")
            if output:
                _emit_log(manager, job_id, str(output)[:300], "tool_result")

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


def _run_ghidra_cmd(cmd: list[str], env: dict, manager: JobManager, job_id: str, phase: str, base_pct: int) -> int:
    """Run a Ghidra headless command with streaming log output. Returns exit code."""
    import subprocess

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)

    func_count = 0
    total_estimate = 20000  # rough estimate, refine from output
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue

        # Parse our DECOMPILE_PROGRESS markers from export script
        if line.startswith("DECOMPILE_PROGRESS:"):
            # Format: "DECOMPILE_PROGRESS: 1234 decompiled, 5 failed, 1239 total"
            try:
                import re
                m = re.search(r'(\d+) decompiled.*?(\d+) total', line)
                if m:
                    func_count = int(m.group(1))
                    total_estimate = int(m.group(2))
                    pct = min(95, base_pct + 10 + int(55 * func_count / max(total_estimate, 1)))
                    manager.emit_progress(job_id, f"Decompiling: {func_count}/{total_estimate}", pct,
                                          f"{func_count} decompiled")
            except Exception:
                pass
        elif line.startswith("EXPORT_PROGRESS:"):
            try:
                import re
                m = re.search(r"(\d+) exported.*?(\d+) total", line)
                if m:
                    exported = int(m.group(1))
                    total_exp = int(m.group(2))
                    pct = min(98, 70 + int(28 * exported / max(total_exp, 1)))
                    manager.emit_progress(job_id, f"Exporting: {exported}/{total_exp}", pct, f"{exported} files written")
            except Exception:
                pass
        elif "Importing" in line:
            manager.emit_progress(job_id, "Importing ROM", base_pct + 5, line[:100])
        elif "Analyzing" in line or "analysis" in line.lower():
            manager.emit_progress(job_id, "Analyzing", base_pct + 15, line[:100])
        elif "Done!" in line:
            manager.emit_progress(job_id, "Finishing", 95, line[:100])

        _emit_log(manager, job_id, line[:200])

    proc.wait()
    return proc.returncode


def run_ghidra_decompile(manager: JobManager, job_id: str, project: Project, config: dict):
    """Run Ghidra decompilation in a single headless call.

    Imports ROM at 0x08000000 via BinaryLoader, sets up GBA memory map,
    creates entry point, imports discovery labels, analyzes, and exports.
    """
    import os
    import shutil
    import subprocess

    ghidra_headless = os.environ.get("GHIDRA_HEADLESS", "/Applications/ghidra_12.0_PUBLIC/support/analyzeHeadless")
    if not os.path.exists(ghidra_headless):
        ghidra_headless = "/opt/homebrew/Cellar/ghidra/12.0/libexec/support/analyzeHeadless"
    if not os.path.exists(ghidra_headless):
        raise FileNotFoundError("analyzeHeadless not found. Set GHIDRA_HEADLESS env var.")

    rom_path = project.rom_path
    if not rom_path.exists():
        raise FileNotFoundError(f"ROM not found: {rom_path}")

    from pathlib import Path
    scripts_dir = Path(__file__).parent.parent / "static_analysis" / "ghidra_scripts"

    ghidra_project_dir = project.ghidra_dir
    ghidra_project_dir.mkdir(parents=True, exist_ok=True)
    project_name = project.name.replace("-", "_")

    # Clean old Ghidra project
    old_rep = ghidra_project_dir / f"{project_name}.rep"
    old_gpr = ghidra_project_dir / f"{project_name}.gpr"
    if old_rep.exists():
        shutil.rmtree(old_rep)
    if old_gpr.exists():
        old_gpr.unlink()

    # Clean old decompiled output
    functions_dir = project.src_dir / "functions"
    if functions_dir.exists():
        shutil.rmtree(functions_dir)
    functions_dir.mkdir(parents=True, exist_ok=True)

    # Export discovery labels
    manager.emit_progress(job_id, "Preparing", 5, "Exporting discovery labels...")
    from rommer.cli.commands.ghidra_decompile import _export_labels
    _export_labels(project)

    output_dir = project.src_dir
    env = os.environ.copy()
    env["ROMMER_OUTPUT_DIR"] = str(output_dir)
    env["ROMMER_LABELS_FILE"] = str(ghidra_project_dir / "discovery_labels.json")

    _emit_log(manager, job_id, f"ROM: {rom_path}")
    _emit_log(manager, job_id, f"Ghidra project: {ghidra_project_dir}/{project_name}")

    # Single headless call: import at 0x08000000, setup memory + entry point,
    # import labels, auto-analyze, then export
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
        "-preScript", str(scripts_dir / "import_labels.py"),
        "-postScript", str(scripts_dir / "export_decompiled.py"),
        "-postScript", str(scripts_dir / "export_split.py"),
        "-scriptPath", str(scripts_dir),
        "-max-cpu", "4",
        "-analysisTimeoutPerFile", "600",
        "-overwrite",
    ]

    _emit_log(manager, job_id, "Starting Ghidra headless (this typically takes 5-15 minutes)...")
    manager.emit_progress(job_id, "Analyzing", 15, "Running Ghidra headless analysis...")

    rc = _run_ghidra_cmd(cmd, env, manager, job_id, "Ghidra", 15)
    if rc != 0:
        raise RuntimeError(f"Ghidra exited with code {rc}")

    # Count output
    func_count = len(list(functions_dir.glob("*.c"))) if functions_dir.exists() else 0
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


def _run_agent_job(agent_class, manager: JobManager, job_id: str, project: Project, config: dict):
    """Generic worker for any agent-based job."""
    model = config.get("model", "opus")
    focus = config.get("focus")

    agent = agent_class(project, focus=focus)
    _emit_log(manager, job_id, f"Spawning {agent.agent_type} agent (model: {model})")
    manager.emit_progress(job_id, "Agent running", 20, f"{agent.agent_type} analyzing...")

    def on_event(event: dict):
        etype = event.get("type", "")
        if etype == "agent_text":
            text = event.get("text", "").strip()
            if text and len(text) > 3:
                _emit_log(manager, job_id, text[:500], "log")
        elif etype == "agent_thinking":
            text = event.get("text", "").strip()
            if text and len(text) > 3:
                _emit_log(manager, job_id, text[:500], "thinking")
        elif etype == "agent_tool_call":
            tool = event.get("tool", "")
            tool_input = event.get("input", {})
            # Format tool call with key details
            detail = ""
            if tool == "Bash":
                detail = f": {tool_input.get('command', '')[:200]}"
            elif tool == "Read":
                detail = f": {tool_input.get('file_path', '')}"
            elif tool in ("Edit", "Write"):
                detail = f": {tool_input.get('file_path', '')}"
            elif tool in ("Grep", "Glob"):
                detail = f": {tool_input.get('pattern', '')}"
            _emit_log(manager, job_id, f"[{tool}]{detail}", "tool_call")
        elif etype == "agent_tool_result":
            output = event.get("output", "")
            if output:
                _emit_log(manager, job_id, str(output)[:300], "tool_result")

    result = agent.spawn(model=model, timeout=1800, on_event=on_event)

    discoveries = 0
    if result and isinstance(result, dict):
        stage = config.get("stage_discoveries", False)
        if stage:
            discoveries = _stage_discoveries(manager, job_id, result)
            _emit_log(manager, job_id, f"Staged {discoveries} discoveries for merge")
        else:
            staged = agent.complete(result)
            discoveries = len(staged)
            if discoveries:
                _emit_log(manager, job_id, f"Proposed {discoveries} discoveries")

        for obs in result.get("observations", []):
            _emit_log(manager, job_id, f"  {obs}")

    summary_parts = [f"{agent.agent_type} complete"]
    if discoveries:
        summary_parts.append(f"{discoveries} discoveries")
    if result and isinstance(result, dict):
        renamed = result.get("renamed_functions", [])
        if renamed:
            summary_parts.append(f"{len(renamed)} functions renamed")
        files_mod = result.get("files_modified")
        if files_mod:
            summary_parts.append(f"{files_mod} files modified")

    manager.complete_job(job_id, " | ".join(summary_parts))


def run_static_analysis(manager: JobManager, job_id: str, project: Project, config: dict):
    from rommer.agents.static_analyzer import StaticAnalyzer
    _run_agent_job(StaticAnalyzer, manager, job_id, project, config)


def run_refactor_type_resolver(manager: JobManager, job_id: str, project: Project, config: dict):
    from rommer.agents.refactor.type_resolver import TypeResolver
    _run_agent_job(TypeResolver, manager, job_id, project, config)


def run_refactor_literal_pool(manager: JobManager, job_id: str, project: Project, config: dict):
    from rommer.agents.refactor.literal_pool import LiteralPoolResolver
    _run_agent_job(LiteralPoolResolver, manager, job_id, project, config)


def run_refactor_forward_decl(manager: JobManager, job_id: str, project: Project, config: dict):
    from rommer.agents.refactor.forward_decl import ForwardDeclGenerator
    _run_agent_job(ForwardDeclGenerator, manager, job_id, project, config)


def run_refactor_struct_annotator(manager: JobManager, job_id: str, project: Project, config: dict):
    from rommer.agents.refactor.struct_annotator import StructAnnotator
    _run_agent_job(StructAnnotator, manager, job_id, project, config)


def run_refactor_system_tracer(manager: JobManager, job_id: str, project: Project, config: dict):
    from rommer.agents.refactor.system_tracer import SystemTracer
    _run_agent_job(SystemTracer, manager, job_id, project, config)


def run_dynamic_analysis(manager: JobManager, job_id: str, project: Project, config: dict):
    """Run dynamic analysis — start emulator server, spawn exploration agent."""
    import os
    import signal
    import subprocess
    import time

    model = config.get("model", "opus")
    focus = config.get("focus")
    save_state = config.get("save_state")
    port = config.get("port", 9123)
    frame_budget = config.get("frame_budget", 50000)

    rom_path = project.rom_path
    if not rom_path.exists():
        raise FileNotFoundError(f"ROM not found: {rom_path}")

    # Find save state
    if save_state:
        state_path = project.save_states_dir / save_state
    else:
        # Use first available save state
        saves = list(project.save_states_dir.iterdir()) if project.save_states_dir.exists() else []
        saves = [s for s in saves if s.is_file() and not s.name.startswith(".")]
        if not saves:
            raise FileNotFoundError("No save states found. Add a save state to save_states/")
        state_path = saves[0]

    if not state_path.exists():
        raise FileNotFoundError(f"Save state not found: {state_path}")

    _emit_log(manager, job_id, f"ROM: {rom_path}")
    _emit_log(manager, job_id, f"Save state: {state_path.name}")
    _emit_log(manager, job_id, f"Port: {port}")

    # Working directory for this agent's evidence
    workdir = project.root / "tmp" / job_id
    workdir.mkdir(parents=True, exist_ok=True)

    # Start emulator server
    _emit_log(manager, job_id, "Starting emulator server...")
    manager.emit_progress(job_id, "Starting emulator", 10, "Launching mGBA server...")

    emu_cmd = [
        "python", "-m", "rommer.emulator.gba.mgba.server",
        "--rom", str(rom_path),
        "--state", str(state_path),
        "--workdir", str(workdir),
        "--port", str(port),
    ]

    emu_env = os.environ.copy()
    mgba_lib = os.environ.get("MGBA_LIB_PATH", "/tmp/mgba-src/build")
    mgba_python = os.environ.get("MGBA_PYTHON_PATH", "/tmp/mgba-src/build/python/lib.macosx-15.0-arm64-cpython-314")
    emu_env["DYLD_LIBRARY_PATH"] = mgba_lib
    emu_env["PYTHONPATH"] = mgba_python + ":" + emu_env.get("PYTHONPATH", "")

    emu_proc = subprocess.Popen(
        emu_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=emu_env,
    )

    # Wait for server to be ready
    time.sleep(3)
    if emu_proc.poll() is not None:
        output = emu_proc.stdout.read()
        raise RuntimeError(f"Emulator server failed to start: {output[:500]}")

    _emit_log(manager, job_id, f"Emulator server running on port {port}")
    manager.emit_progress(job_id, "Agent exploring", 20, "Agent spawned...")

    try:
        # Spawn the agent
        from rommer.agents.dynamic_analyzer import DynamicAnalyzer
        agent = DynamicAnalyzer(
            project, focus=focus, server_port=port,
            frame_budget=frame_budget, save_state=save_state,
        )

        def on_event(event: dict):
            etype = event.get("type", "")
            if etype == "agent_text":
                text = event.get("text", "").strip()
                if text and len(text) > 3:
                    _emit_log(manager, job_id, text[:300])
            elif etype == "agent_tool_call":
                tool = event.get("tool", "")
                _emit_log(manager, job_id, f"[tool] {tool}")

        result = agent.spawn(model=model, timeout=1800, on_event=on_event)

        discoveries = 0
        if result and isinstance(result, dict):
            stage = config.get("stage_discoveries", False)
            if stage:
                discoveries = _stage_discoveries(manager, job_id, result)
                _emit_log(manager, job_id, f"Staged {discoveries} discoveries for merge")
            else:
                staged = agent.complete(result)
                discoveries = len(staged)
                if discoveries:
                    _emit_log(manager, job_id, f"Discovered {discoveries} addresses")

            for obs in result.get("observations", []):
                _emit_log(manager, job_id, f"  {obs}")

        manager.complete_job(job_id, f"Found {discoveries} discoveries")

    finally:
        # Kill emulator server
        _emit_log(manager, job_id, "Stopping emulator server...")
        try:
            emu_proc.terminate()
            emu_proc.wait(timeout=5)
        except Exception:
            emu_proc.kill()

        # Clean up workdir
        import shutil
        if workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)


def run_build_tree(manager: JobManager, job_id: str, project: Project, config: dict):
    """Build the function call graph from decompiled code."""
    _emit_log(manager, job_id, "Building function call graph...")
    manager.emit_progress(job_id, "Building tree", 10, "Parsing function calls...")

    from rommer.cli.commands.build_tree import build_call_graph
    platform = config.get("platform", project.project_json.get("platform", "gba"))
    graph = build_call_graph(project.src_dir, platform=platform)

    _emit_log(manager, job_id, f"Tree built: {graph['total_functions']} functions, {graph['max_depth']} levels deep")
    _emit_log(manager, job_id, f"  Leaves: {graph['leaf_count']}, Roots: {graph['root_count']}, Cycles: {graph['cycle_count']}")

    manager.complete_job(job_id, f"Call graph: {graph['total_functions']} functions, {graph['max_depth']} levels")


def run_function_analysis(manager: JobManager, job_id: str, project: Project, config: dict):
    """Analyze a chunk of functions for the bottom-up pipeline."""
    model = config.get("model", "opus")
    chunk = config.get("chunk", [])  # list of {address, file_path, ...}
    level = config.get("level", 0)

    if not chunk:
        manager.fail_job(job_id, "No functions in chunk")
        return

    _emit_log(manager, job_id, f"Analyzing {len(chunk)} functions at level {level} (model: {model})")
    manager.emit_progress(job_id, f"Level {level}: Loading", 5, f"Loading {len(chunk)} functions...")

    # Load call graph for augmentation data
    call_graph_path = project.src_dir / "call_graph.json"
    call_graph = {}
    if call_graph_path.exists():
        call_graph = json.loads(call_graph_path.read_text()).get("functions", {})

    # Load existing function analyses (child summaries)
    child_cache: dict[str, dict] = {}
    try:
        conn = project.get_db()
        p = "%s" if hasattr(conn, '_conn') else "?"
        rows = conn.execute(
            f"SELECT address, name, system, description, confidence FROM function_analysis WHERE project_id = (SELECT id FROM project LIMIT 1)"
        ).fetchall()
        for r in rows:
            child_cache[r["address"]] = dict(r)
        conn.close()
    except Exception:
        pass

    # Build function data for the agent
    funcs_dir = project.src_dir / "functions"
    func_data = []

    for func_info in chunk:
        addr = func_info.get("address", "")
        name = func_info.get("name", "")

        # Find the .c file
        file_path = None
        for f in funcs_dir.glob(f"{addr.replace('0x', '')}*.c"):
            file_path = f
            break

        if not file_path or not file_path.exists():
            continue

        code = file_path.read_text()

        # Get augmentation from call graph
        cg_entry = call_graph.get(name, {})
        callees = cg_entry.get("callees", [])

        # Build child summaries
        child_summaries = []
        for callee in callees:
            callee_entry = call_graph.get(callee, {})
            callee_addr = callee_entry.get("address", "")
            if callee_addr in child_cache:
                child_summaries.append(child_cache[callee_addr])

        func_data.append({
            "address": addr,
            "original_name": name,
            "code": code,
            "file_path": str(file_path),
            "child_summaries": child_summaries,
            "discovery_refs": cg_entry.get("discovery_refs"),
            "io_registers": cg_entry.get("io_registers"),
            "level": level,
        })

    if not func_data:
        manager.complete_job(job_id, "No function files found for chunk")
        return

    _emit_log(manager, job_id, f"Loaded {len(func_data)} function files")
    manager.emit_progress(job_id, f"Level {level}: Analyzing", 15, f"Agent analyzing {len(func_data)} functions...")

    # Spawn agent
    from rommer.agents.function_analyzer import FunctionAnalyzer
    analyzer = FunctionAnalyzer(project, functions=func_data)

    analyzed_count = [0]

    def on_event(event: dict):
        etype = event.get("type", "")
        if etype == "agent_text":
            text = event.get("text", "").strip()
            if text and len(text) > 3:
                _emit_log(manager, job_id, text[:500], "log")
        elif etype == "agent_thinking":
            text = event.get("text", "").strip()
            if text and len(text) > 3:
                _emit_log(manager, job_id, text[:500], "thinking")
        elif etype == "agent_tool_call":
            tool = event.get("tool", "")
            tool_input = event.get("input", {})
            detail = ""
            if tool == "Bash":
                detail = f": {tool_input.get('command', '')[:200]}"
            elif tool == "Read":
                detail = f": {tool_input.get('file_path', '')}"
            _emit_log(manager, job_id, f"[{tool}]{detail}", "tool_call")

    result = analyzer.spawn(model=model, timeout=3600, on_event=on_event)

    if result:
        staged = analyzer.complete(result)
        analyzed_count[0] = len(staged)
        _emit_log(manager, job_id, f"Analyzed {len(staged)} functions")
        manager.emit_progress(job_id, f"Level {level}", 50, f"Analyzed {len(staged)}/{len(chunk)}, renaming files...")

        # Rename files for analyzed functions
        rename_count = 0
        for a in staged:
            addr = a.get("address", "").replace("0x", "").upper()
            new_name = a.get("name", "")
            if not addr or not new_name or new_name.startswith("FUN_"):
                continue

            for f in funcs_dir.glob(f"{addr}*.c"):
                new_path = f.parent / f"{addr}_{new_name}.c"
                if new_path != f:
                    # Add header comment
                    content = f.read_text()
                    header = (
                        f"// Function: {new_name}\n"
                        f"// Address:  0x{addr}\n"
                        f"// System:   {a.get('system', 'unknown')}\n"
                        f"// Confidence: {a.get('confidence', 0)}\n"
                        f"// Completeness: {a.get('completeness', 0)}\n"
                        f"//\n"
                        f"// {a.get('description', '')}\n"
                    )
                    # Replace existing header
                    if content.startswith("// Function:"):
                        content = content[content.index("\n\n") + 2:]
                    content = header + "\n" + content
                    new_path.write_text(content)
                    if new_path != f:
                        f.unlink()
                    rename_count += 1
                    pct = min(95, 50 + int(45 * rename_count / max(len(staged), 1)))
                    manager.emit_progress(job_id, f"Level {level}", pct, f"Renamed {rename_count}/{len(staged)}")
                    _emit_log(manager, job_id, f"Renamed: {f.name} → {new_path.name}")
                break

    manager.complete_job(job_id, f"Analyzed {analyzed_count[0]}/{len(chunk)} functions at level {level}")


def run_code_cleanup(manager: JobManager, job_id: str, project: Project, config: dict):
    """Clean Ghidra artifacts from a chunk of functions."""
    model = config.get("model", "opus")
    chunk = config.get("chunk", [])
    level = config.get("level", 0)

    if not chunk:
        manager.fail_job(job_id, "No functions in chunk")
        return

    _emit_log(manager, job_id, f"Cleaning {len(chunk)} functions at level {level} (model: {model})")
    manager.emit_progress(job_id, f"Cleanup L{level}", 5, f"Loading {len(chunk)} functions...")

    funcs_dir = project.src_dir / "functions"
    func_data = []

    for func_info in chunk:
        addr = func_info.get("address", "")
        file_path = None
        for f in funcs_dir.glob(f"{addr.replace('0x', '')}*.c"):
            file_path = f
            break
        if not file_path or not file_path.exists():
            continue
        func_data.append({
            "address": addr,
            "code": file_path.read_text(),
            "file_path": str(file_path),
        })

    if not func_data:
        manager.complete_job(job_id, "No function files found")
        return

    _emit_log(manager, job_id, f"Loaded {len(func_data)} function files")
    manager.emit_progress(job_id, f"Cleanup L{level}", 15, f"Agent cleaning {len(func_data)} functions...")

    from rommer.agents.code_cleanup import CodeCleanupAgent
    agent = CodeCleanupAgent(project, functions=func_data)

    def on_event(event: dict):
        etype = event.get("type", "")
        if etype == "agent_text":
            text = event.get("text", "").strip()
            if text and len(text) > 3:
                _emit_log(manager, job_id, text[:500], "log")
        elif etype == "agent_thinking":
            text = event.get("text", "").strip()
            if text and len(text) > 3:
                _emit_log(manager, job_id, text[:500], "thinking")
        elif etype == "agent_tool_call":
            tool = event.get("tool", "")
            _emit_log(manager, job_id, f"[{tool}]", "tool_call")

    result = agent.spawn(model=model, timeout=3600, on_event=on_event)

    cleaned_count = 0
    if result:
        # Result is array of {address, cleaned_code}
        items = result if isinstance(result, list) else result.get("functions", [result])
        for item in items:
            addr = item.get("address", "").replace("0x", "").upper()
            cleaned = item.get("cleaned_code", "")
            if not addr or not cleaned:
                continue

            for f in funcs_dir.glob(f"{addr}*.c"):
                f.write_text(cleaned)
                cleaned_count += 1
                _emit_log(manager, job_id, f"Cleaned: {f.name}")
                break

        pct = min(95, 50 + int(45 * cleaned_count / max(len(func_data), 1)))
        manager.emit_progress(job_id, f"Cleanup L{level}", pct, f"Cleaned {cleaned_count}/{len(func_data)}")

    manager.complete_job(job_id, f"Cleaned {cleaned_count}/{len(chunk)} functions at level {level}")


# Registry of job types to worker functions
WORKERS = {
    "graph_gen": run_graph_gen,
    "knowledge_analysis": run_knowledge_analysis,
    "ghidra_decompile": run_ghidra_decompile,
    "build_tree": run_build_tree,
    "static_analysis": run_static_analysis,
    "dynamic_analysis": run_dynamic_analysis,
    "type_resolver": run_refactor_type_resolver,
    "literal_pool": run_refactor_literal_pool,
    "forward_decl": run_refactor_forward_decl,
    "struct_annotator": run_refactor_struct_annotator,
    "system_tracer": run_refactor_system_tracer,
    "function_analysis": run_function_analysis,
    "code_cleanup": run_code_cleanup,
}

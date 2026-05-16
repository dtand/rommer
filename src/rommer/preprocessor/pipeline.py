"""Orchestrates the 5-pass preprocessor pipeline.

Each pass wraps a Claude Code CLI invocation. Claude reads the
walkthrough file directly via its Read tool.
"""

import json
from pathlib import Path

from rommer.config import Project
from rommer.preprocessor.pass1_structure import detect_structure
from rommer.preprocessor.pass2_systems import audit_systems
from rommer.preprocessor.pass3_extraction import extract_data
from rommer.preprocessor.pass4_graph import generate_graph
from rommer.preprocessor.pass5_augment import augment_nodes


def run_pipeline(project: Project, model: str = "opus") -> dict:
    """Run all 5 passes of the preprocessor.

    Returns a dict with the accumulated output from each pass.
    """
    output_dir = project.graph_dir / "preprocessor_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find walkthrough file
    guides_dir = project.knowledge_dir / "guides"
    wt_files = list(guides_dir.glob("walkthrough*")) if guides_dir.exists() else []
    if not wt_files:
        raise FileNotFoundError(f"No walkthrough file found in {guides_dir}")
    wt_path = wt_files[0]

    results = {}

    # Pass 1: Structure Detection
    print("=== Pass 1: Structure Detection ===")
    section_map = detect_structure(model, wt_path)
    results["section_map"] = section_map
    _save(output_dir / "pass1_section_map.json", section_map)
    print(f"  Found {len(section_map.get('sections', []))} sections")

    # Pass 2: System Audit + Schema Proposal
    print("=== Pass 2: System Audit + Schema ===")
    systems = audit_systems(model, wt_path, section_map)
    results["systems"] = systems
    _save(output_dir / "pass2_systems.json", systems)
    print(f"  Proposed {len(systems.get('game_systems', []))} game systems")

    # Pass 3: Data Extraction
    print("=== Pass 3: Data Extraction ===")
    data = extract_data(model, wt_path, section_map, systems)
    results["data"] = data
    _save(output_dir / "pass3_data.json", data)
    print(f"  Extracted {sum(len(v) for v in data.get('tables', {}).values())} rows")

    # Pass 4: Graph Generation
    print("=== Pass 4: Graph Generation ===")
    graph = generate_graph(model, wt_path, section_map, systems, data)
    results["graph"] = graph
    _save(output_dir / "pass4_graph.json", graph)
    print(f"  Generated {len(graph.get('nodes', []))} nodes, {len(graph.get('edges', []))} edges")

    # Pass 5: Augmentation (tagging + knowledge linking)
    print("=== Pass 5: Augmentation ===")
    augment_result = augment_nodes(project, model)
    results["augment"] = augment_result
    _save(output_dir / "pass5_augment.json", augment_result)
    print(f"  Tagged {augment_result.get('tagged_count', 0)} nodes")
    print(f"  Linked {augment_result.get('links_created', 0)} knowledge resources")

    return results


def _save(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2))

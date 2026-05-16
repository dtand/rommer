"""rommer build-graph - run walkthrough graph generation pipeline."""

from rommer.config import Project


def handler(args):
    project = Project(args.project)
    if not project.exists():
        print(f"Error: project '{args.project}' not found")
        raise SystemExit(1)

    if args.dry_run:
        print(f"build-graph: {args.project} (dry-run)")
        print("  Pass 1: Structure detection")
        print("  Pass 2: System audit + schema")
        print("  Pass 3: Data extraction")
        print("  Pass 4: Graph generation")
        print("  Pass 5: Augmentation (tagging + knowledge linking)")
        print(f"  Model: {args.model}")
        return

    from rommer.preprocessor.pipeline import run_pipeline
    from rommer.db.models import init_db

    # Ensure DB has schema
    conn = project.get_db()
    init_db(conn)
    conn.close()

    walkthrough = getattr(args, 'walkthrough', None)
    print(f"Running build-graph for: {args.project}")
    print(f"Model: {args.model}")
    if walkthrough:
        print(f"Walkthrough: {walkthrough}")
    print()

    results = run_pipeline(project, model=args.model, walkthrough=walkthrough)

    print()
    print("=== Pipeline Complete ===")
    if "graph" in results:
        graph = results["graph"]
        print(f"  Nodes: {len(graph.get('nodes', []))}")
        print(f"  Edges: {len(graph.get('edges', []))}")

    # Store results in DB
    _store_results(project, results)


def _store_results(project: Project, results: dict):
    """Store pipeline results in the project database."""
    import json

    conn = project.get_db()

    # Get or create project row
    row = conn.execute("SELECT id FROM project LIMIT 1").fetchone()
    if not row:
        conn.execute(
            "INSERT INTO project (game_id, game_title) VALUES (?, ?)",
            (project.name, project.name),
        )
        conn.commit()
        row = conn.execute("SELECT id FROM project LIMIT 1").fetchone()
    project_id = row[0]

    # Store sections (pass 1)
    section_map = results.get("section_map", {})
    for section in section_map.get("sections", []):
        conn.execute(
            """INSERT OR REPLACE INTO section
               (project_id, section_id, title, type, line_start, line_end, description)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (project_id, section.get("section_id"), section.get("title"),
             section.get("type"), section.get("line_start"), section.get("line_end"),
             section.get("description")),
        )

    # Store game systems (pass 2)
    systems = results.get("systems", {})
    for system in systems.get("game_systems", []):
        conn.execute(
            """INSERT OR REPLACE INTO game_system (project_id, name, description, table_names)
               VALUES (?, ?, ?, ?)""",
            (project_id, system.get("name"), system.get("description"),
             json.dumps(system.get("table_names", []))),
        )

    # Store control mappings
    for ctrl in systems.get("control_mappings", []):
        conn.execute(
            """INSERT INTO control_mapping (project_id, context, button, action)
               VALUES (?, ?, ?, ?)""",
            (project_id, ctrl.get("context"), ctrl.get("button"), ctrl.get("action")),
        )

    # Store schema SQL
    if systems.get("schema_sql"):
        conn.execute(
            "INSERT INTO schema_sql (project_id, sql_text) VALUES (?, ?)",
            (project_id, systems["schema_sql"]),
        )

    # Store data tables (pass 3)
    data = results.get("data", {})
    for table_name, rows in data.get("tables", {}).items():
        if not rows:
            continue
        columns = list(rows[0].keys()) if isinstance(rows[0], dict) else []
        conn.execute(
            "INSERT INTO game_data_table (project_id, table_name, column_names) VALUES (?, ?, ?)",
            (project_id, table_name, json.dumps(columns)),
        )
        table_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for i, row in enumerate(rows):
            conn.execute(
                "INSERT INTO game_data_row (table_id, row_index, row_data) VALUES (?, ?, ?)",
                (table_id, i, json.dumps(row)),
            )

    # Store graph nodes (pass 4)
    graph = results.get("graph", {})
    for i, node in enumerate(graph.get("nodes", [])):
        conn.execute(
            """INSERT OR REPLACE INTO graph_node
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

    # Store edges
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

    node_count = len(graph.get("nodes", []))
    edge_count = len(graph.get("edges", []))
    if node_count:
        print(f"  Stored {node_count} nodes, {edge_count} edges in DB")

"""rommer nuke - clean up node data (DB records + filesystem)."""

import shutil
import sqlite3

from rommer.config import Project


def handler(args):
    project = Project(args.project)
    if not project.exists():
        print(f"Error: project '{args.project}' not found")
        raise SystemExit(1)

    if not args.force and not args.node:
        print("Error: specify --force or --node NODE_ID")
        raise SystemExit(1)

    nodes_dir = project.graph_dir / "nodes"
    db_path = project.db_path

    # Determine which nodes to nuke
    nodes = []
    if args.force:
        # Discover from filesystem
        if nodes_dir.exists():
            nodes = [d.name for d in nodes_dir.iterdir() if d.is_dir()]
        # Discover from DB
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.execute(
                    "SELECT DISTINCT node_id FROM execution_run "
                    "UNION SELECT DISTINCT node_id FROM node_candidate "
                    "UNION SELECT DISTINCT discovered_by_node FROM discovery"
                )
                for row in cursor:
                    if row[0] and row[0] not in nodes:
                        nodes.append(row[0])
                conn.close()
            except sqlite3.OperationalError:
                pass
    else:
        nodes = args.node or []

    if not nodes:
        print("Nothing to clean up.")
        return

    # Show what will be deleted
    print(f"Project: {args.project}")
    print(f"DB: {db_path}")
    print()
    print("Nodes to nuke:")
    for node in nodes:
        node_dir = nodes_dir / node
        fs_status = "(no dir)"
        if node_dir.exists():
            file_count = sum(1 for _ in node_dir.rglob("*") if _.is_file())
            fs_status = f"{file_count} files"

        db_counts = ""
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                d = conn.execute("SELECT COUNT(*) FROM discovery WHERE discovered_by_node=?", (node,)).fetchone()[0]
                r = conn.execute("SELECT COUNT(*) FROM execution_run WHERE node_id=?", (node,)).fetchone()[0]
                c = conn.execute("SELECT COUNT(*) FROM node_candidate WHERE node_id=?", (node,)).fetchone()[0]
                db_counts = f"discoveries={d}, runs={r}, candidates={c}"
                conn.close()
            except sqlite3.OperationalError:
                db_counts = "(no matching tables)"

        print(f"  {node}: {fs_status} | {db_counts}")

    print()

    # Confirm
    if not args.y:
        answer = input("Proceed? [y/N] ")
        if answer.lower() != "y":
            print("Aborted.")
            raise SystemExit(1)

    # Delete
    for node in nodes:
        print(f"Nuking {node}...")

        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                conn.execute("DELETE FROM discovery WHERE discovered_by_node=?", (node,))
                conn.execute("DELETE FROM node_candidate WHERE node_id=?", (node,))
                conn.execute("DELETE FROM execution_run WHERE node_id=?", (node,))
                conn.commit()
                conn.close()
                print("  DB rows deleted")
            except sqlite3.OperationalError:
                pass

        node_dir = nodes_dir / node
        if node_dir.exists():
            shutil.rmtree(node_dir)
            print(f"  Directory removed: nodes/{node}/")

    print()
    print("Done.")

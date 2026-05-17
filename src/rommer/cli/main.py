"""Rommer CLI - unified command interface."""

import argparse
import sys

from rommer.cli.commands import init_project, build_graph, build_tree, build_brief, ghidra_decompile, launch_agent, emulator, worker, nuke


def main():
    parser = argparse.ArgumentParser(
        prog="rommer",
        description="AI-driven reverse engineering platform for GBA ROMs",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init-project
    sp = subparsers.add_parser("init-project", help="Initialize a new project workspace")
    sp.add_argument("--name", required=True, help="Project name")
    sp.add_argument("--platform", default="gba", help="Platform (default: gba)")
    sp.add_argument("--zip", help="Path to ZIP file with game resources")

    # build-graph
    sp = subparsers.add_parser("build-graph", help="Run walkthrough graph generation pipeline")
    sp.add_argument("--project", required=True, help="Project name")
    sp.add_argument("--model", default="opus", help="Model to use (default: opus)")
    sp.add_argument("--walkthrough", help="Specific walkthrough filename to use")
    sp.add_argument("--dry-run", action="store_true", help="Show pipeline steps without executing")

    # build-brief
    sp = subparsers.add_parser("build-brief", help="Generate condensed game brief from project data")
    sp.add_argument("--project", required=True, help="Project name")

    # build-tree
    sp = subparsers.add_parser("build-tree", help="Build function call graph from decompiled code")
    sp.add_argument("--project", required=True, help="Project name")

    # ghidra-decompile
    sp = subparsers.add_parser("ghidra-decompile", help="Run full Ghidra decompilation workflow")
    sp.add_argument("--project", required=True, help="Project name")
    sp.add_argument("--dry-run", action="store_true", help="Show workflow steps without executing")

    # launch-agent
    sp = subparsers.add_parser("launch-agent", help="Spawn an analysis agent")
    sp.add_argument("--project", required=True, help="Project name")
    sp.add_argument("--agent", required=True, choices=["dynamic", "static", "refactor"], help="Agent type")
    sp.add_argument("--focus", help="Focus area for the agent")
    sp.add_argument("--save-state", help="Save state to load")
    sp.add_argument("--parallel", type=int, default=1, help="Number of parallel agents")
    sp.add_argument("--stage", help="Refactor pipeline stage (for refactor agent)")
    sp.add_argument("--dry-run", action="store_true", help="Show what would run without executing")

    # emulator
    sp = subparsers.add_parser("emulator", help="Launch mGBA with a project's ROM and save state")
    sp.add_argument("--project", required=True, help="Project name")
    sp.add_argument("--save-state", help="Save state filename (default: first available)")
    sp.add_argument("--headless", action="store_true", help="Run as TCP server instead of GUI")
    sp.add_argument("--port", type=int, default=9123, help="TCP port for headless mode (default: 9123)")

    # worker
    sp = subparsers.add_parser("worker", help="Manage the job worker daemon")
    sp.add_argument("action", choices=["start", "stop", "status"], help="Daemon action")
    sp.add_argument("--max-workers", type=int, default=4, help="Max concurrent workers (default: 4)")

    # nuke
    sp = subparsers.add_parser("nuke", help="Clean up node data (DB + filesystem)")
    sp.add_argument("--project", required=True, help="Project name")
    sp.add_argument("--node", action="append", help="Specific node(s) to nuke")
    sp.add_argument("--force", action="store_true", help="Nuke ALL nodes")
    sp.add_argument("-y", action="store_true", help="Skip confirmation")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Route to handler
    handlers = {
        "init-project": init_project.handler,
        "build-graph": build_graph.handler,
        "build-tree": build_tree.handler,
        "build-brief": build_brief.handler,
        "ghidra-decompile": ghidra_decompile.handler,
        "launch-agent": launch_agent.handler,
        "emulator": emulator.handler,
        "worker": worker.handler,
        "nuke": nuke.handler,
    }

    handler = handlers[args.command]
    handler(args)

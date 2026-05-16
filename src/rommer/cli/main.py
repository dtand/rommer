"""Rommer CLI - unified command interface."""

import argparse
import sys

from rommer.cli.commands import init_project, build_graph, ghidra_decompile, launch_agent, nuke


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
    sp.add_argument("--dry-run", action="store_true", help="Show pipeline steps without executing")

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
        "ghidra-decompile": ghidra_decompile.handler,
        "launch-agent": launch_agent.handler,
        "nuke": nuke.handler,
    }

    handler = handlers[args.command]
    handler(args)

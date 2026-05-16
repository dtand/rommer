"""rommer launch-agent - spawn an analysis agent."""

from rommer.config import Project


def handler(args):
    project = Project(args.project)
    if not project.exists():
        print(f"Error: project '{args.project}' not found")
        raise SystemExit(1)

    if args.dry_run:
        print(f"launch-agent: {args.project} (dry-run)")
        print(f"  Agent type: {args.agent}")
        print(f"  Focus: {args.focus or '(none)'}")
        print(f"  Parallel: {args.parallel}")
        if args.agent == "refactor":
            print(f"  Stage: {args.stage or '(all stages)'}")
        if args.save_state:
            print(f"  Save state: {args.save_state}")
        return

    # TODO: Import agent classes and spawn
    print("Error: launch-agent execution not yet implemented")
    raise SystemExit(1)

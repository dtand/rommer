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

    # TODO: Import and run preprocessor pipeline
    print("Error: build-graph execution not yet implemented")
    raise SystemExit(1)

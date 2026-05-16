"""rommer init-project - scaffold a new project workspace."""

from rommer.config import Project


def handler(args):
    if Project(args.name).exists():
        print(f"Error: project '{args.name}' already exists")
        raise SystemExit(1)

    project = Project.scaffold(args.name, args.platform)
    print(f"Created project workspace: {project.root}")

    if args.zip:
        # TODO: Extract ZIP, classify files, validate resources
        print(f"  ZIP processing not yet implemented (file: {args.zip})")
    else:
        print("  No ZIP provided - empty workspace created")
        print(f"  Add ROM to: {project.root / 'rom/'}")
        print(f"  Add knowledge to: {project.root / 'knowledge/'}")

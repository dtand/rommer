"""rommer launch-agent - spawn an analysis agent."""

from rommer.config import Project


def handler(args):
    project = Project(args.project)
    if not project.exists():
        print(f"Error: project '{args.project}' not found")
        raise SystemExit(1)

    from rommer.agents.dynamic_analyzer import DynamicAnalyzer
    from rommer.agents.static_analyzer import StaticAnalyzer
    from rommer.agents.refactor import PIPELINE_ORDER

    agent_map = {
        "dynamic": DynamicAnalyzer,
        "static": StaticAnalyzer,
    }

    if args.agent == "refactor":
        if args.stage:
            # Find specific stage
            stage_cls = None
            for cls in PIPELINE_ORDER:
                if args.stage in cls.__name__.lower() or args.stage in cls(project).agent_type:
                    stage_cls = cls
                    break
            if not stage_cls:
                print(f"Error: unknown refactor stage '{args.stage}'")
                print(f"Available: {[c.__name__ for c in PIPELINE_ORDER]}")
                raise SystemExit(1)
            agent = stage_cls(project, focus=args.focus)
        else:
            # Run full pipeline
            if args.dry_run:
                print(f"launch-agent: {args.project} (dry-run)")
                print(f"  Agent type: refactor (full pipeline)")
                for cls in PIPELINE_ORDER:
                    print(f"    Stage: {cls.__name__}")
                return
            # TODO: Run pipeline sequentially
            print("Error: full refactor pipeline not yet implemented")
            raise SystemExit(1)
    else:
        agent_cls = agent_map.get(args.agent)
        if not agent_cls:
            print(f"Error: unknown agent type '{args.agent}'")
            raise SystemExit(1)
        agent = agent_cls(project, focus=args.focus)

    if args.dry_run:
        print(f"launch-agent: {args.project} (dry-run)")
        agent.spawn(dry_run=True)
        return

    result = agent.spawn()
    if result:
        staged = agent.complete(result)
        print(f"Agent completed. Staged {len(staged)} candidates.")

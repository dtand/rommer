# Rommer - AI-Driven GBA Reverse Engineering Platform

## Project Structure
```
src/rommer/
  cli/commands/          — CLI commands (init-project, build-graph, build-tree, build-brief,
                           preprocess, cleanup, static-analyze, ghidra-decompile, emulator, worker, nuke)
  agents/                — AI agents (function_analyzer, code_cleanup, knowledge_analyzer,
                           dynamic_analyzer, static_analyzer, refactor/)
  backend/routers/       — FastAPI endpoints (project, graph, jobs, upload, ws, analysis)
  jobs/                  — Job system (manager, daemon, runner, worker, merge)
  db/                    — Database (connection, models, migrate, postgres_schema.sql)
  emulator/gba/mgba/     — mGBA emulator wrapper (core, server, session)
  preprocessor/          — Walkthrough pipeline (passes 1-5, claude.py wrapper)
  scripts/               — Deterministic preprocessing (resolve_types, resolve_literals, generate_headers)
  rom/                   — ROM parsing (gba_header.py)
  knowledge/             — Knowledge processing (code_parser.py)
  config.py              — Project workspace management
web/                     — React + Vite + Tailwind frontend
scripts/                 — dev.sh, refactor_loop.py
```

## Key Architecture Decisions
- **Postgres** for shared state (DATABASE_URL env var), SQLite as fallback
- **Worker daemon** (`rommer worker start`) picks up pending jobs, runs as subprocesses
- **All agents write discoveries as scratch tier**, user promotes to golden via UI
- **Agents use tmp/{uuid}** for scratch files, must clean up
- **Bottom-up tree walking** for cleanup and static analysis (leaves → root, parallel per level)
- **Call graph augmented** with discovery refs via literal pool resolution from ROM binary

## Current Pipeline (in order)
1. init-project (upload ZIP, classify files, validate ROM)
2. Schema generation (passes 1-3, blocking)
3. Knowledge analysis (background, produces discoveries)
4. Ghidra decompile (background, user-initiated)
5. Preprocess (deterministic: types, literals, headers)
6. Build tree (call graph + augment with discoveries)
7. Build brief (condensed game context doc)
8. Code cleanup (agent-driven, bottom-up, syntax verified)
9. Static analysis (agent-driven, bottom-up, names/classifies functions)
10. Dynamic analysis (emulator-based, user-initiated)

## Active Project: robattle (Medabots RPG)
- 16,191 decompiled functions, 11 levels deep in call tree
- 29 golden discoveries (medals, cash, medaparts, items, battle, audio)
- 97 functions augmented with discovery refs + IO registers
- Cleanup running: ~580 cleaned with 100% syntax pass rate
- Code at ~/.rommer/projects/robattle/

## Environment
- Python 3.14, venv at .venv/
- Postgres 15 (local, database: rommer)
- mGBA at ~/Desktop/ROMS/mGBA.app, lib at /tmp/mgba-src/build
- Ghidra 12.0 at /Applications/ghidra_12.0_PUBLIC/
- All env vars in .env (loaded on import)

## Start Services
```bash
./scripts/dev.sh  # backend (8000) + worker daemon + frontend (5174)
```

## Known Issues / TODOs
- Upload flow: only auto-kick knowledge analysis, NOT graph/ghidra. Add "start" buttons in UI
- Analysis page pipeline control panel: show status + re-run buttons for each pipeline step
- Graph gen: output too large for stdout, agent writes to file (still has timeout issues)
- Discovery consensus system: track per-agent observations, auto-promote above threshold
- Normalize system names in function_analysis (robattle-combat vs robattle_combat)
- DB insert per log event may be slow — optimize with batched writes later
- Job log streaming: per-job WebSocket channels implemented but needs testing

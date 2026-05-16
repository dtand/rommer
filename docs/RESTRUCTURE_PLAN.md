# Rommer Restructure Plan

## Vision

Rommer is a GBA ROM reverse engineering platform that uses AI agents (static + dynamic analysis) to decompile, annotate, and understand game ROMs. It takes a ZIP of game resources as input and produces annotated source code, a memory map, and a game walkthrough graph.

Future: extensible to other platforms (GB, NES, SNES) but GBA-only for now.

---

## 1. Project Structure

### 1.1 Rommer System (this repo)

```
rommer/
  src/
    rommer/
      cli/                    # CLI commands (command/handler pattern)
        __init__.py
        main.py               # Entry point, command router
        commands/
          init_project.py     # Scaffold workspace from ZIP
          build_graph.py      # Run graph generation pipeline
          ghidra_decompile.py # Full Ghidra workflow
          launch_agent.py     # Spawn agent by type: --agent static|dynamic|refactor
          nuke.py             # Clean node/project data

      agents/                 # Agent implementations (OOP, base class)
        __init__.py
        base.py               # BaseAgent: spawn(), complete(), context building
        dynamic_analyzer.py   # Explore mode: emulator + memory analysis
        static_analyzer.py    # Decompiled code annotation + xref tracing
        refactor/             # Multi-stage refactor pipeline
          type_resolver.py    # Fix Ghidra types (undefined4, byte, uint)
          literal_pool.py     # Resolve DAT_ references from ROM binary
          forward_decl.py     # Generate function prototypes/headers
          struct_annotator.py # Rewrite pointer math to struct access
          system_tracer.py    # High-level system documentation

      emulator/               # Emulator abstraction layer
        __init__.py
        base.py               # BaseEmulator interface (platform-agnostic)
        gba/                  # GBA platform
          __init__.py
          base.py             # GBAEmulator base (GBA-specific memory map, etc.)
          mgba/               # mGBA implementation
            core.py           # MgbaEmulator(GBAEmulator) wrapper
            server.py         # TCP server for agent commands
          # Future: vba/      # VisualBoyAdvance implementation
        # Future: gb/         # Game Boy platform
        # Future: nes/        # NES platform

      preprocessor/           # Walkthrough → graph pipeline
        __init__.py
        pipeline.py           # Orchestrates all passes
        pass1_structure.py    # Section detection
        pass2_systems.py      # System audit + schema proposal
        pass3_extraction.py   # Data extraction from walkthrough
        pass4_graph.py        # Node DAG generation
        pass5_augment.py      # Tagging + knowledge linking (replaces pass4b)
        prompts/

      backend/                # FastAPI REST API
        __init__.py
        main.py
        routers/

      db/                     # Database utilities
        __init__.py
        connection.py
        models.py
        migrate.py
        ingest.py

      static_analysis/        # Ghidra integration
        __init__.py
        ghidra_client.py      # ghidra-bridge client
        ghidra_scripts/       # Jython scripts for headless Ghidra
          setup_memory.py
          import_labels.py
          export_decompiled.py
          export_split.py

      config.py               # Project/workspace path resolution

  web/                        # React frontend
  scripts/                    # Dev/utility shell scripts
  docs/                       # Architecture docs, plans
```

### 1.2 Project Workspace (per-game, lives at $ROMMER_PROJECTS_ROOT)

```
~/.rommer/projects/{project_name}/
  project.json              # Metadata: name, platform, rom_hash, created_at

  rom/
    game.gba                # The ROM file

  knowledge/                # Supplementary resources (from ZIP upload)
    maps/                   # Map layout images
    guides/                 # Walkthroughs, manuals, PDFs
    codes/                  # AR/CodeBreaker codes
    saves/                  # Provided save files (.sav, .xps)
    misc/                   # Anything else

  graph/                    # Walkthrough graph data
    nodes/                  # Per-node directories
      node_001/
        evidence/           # Screenshots from agent runs
        explore_0/          # Parallel explore agent outputs
        result.json
        candidates.json
        systems.json
    preprocessor_output/    # Intermediate pipeline results

  db/
    rommer.db               # SQLite database
    schema.sql              # Generated schema

  save_states/              # Normalized save states for analysis
    entrypoint.ss0
    100_percent.ss0
    100_percent.sav

  src/                      # Decompiled source code
    CLAUDE.md               # Static analysis agent instructions
    functions/              # Individual function .c files
    include/                # Header files (game_types.h, etc.)
    docs/                   # Analysis logs, system documentation
    proposed_discoveries.json

  ghidra/                   # Ghidra project files
    {project_name}.gdb      # Ghidra project
    discovery_labels.json   # Labels for Ghidra import
```

---

## 2. CLI Design (Command/Handler Pattern)

```
rommer init-project --name medabots-rpg --platform gba --zip ~/uploads/medabots.zip
rommer build-graph --project medabots-rpg [--model opus]
rommer ghidra-decompile --project medabots-rpg
rommer launch-agent --project medabots-rpg --agent dynamic --focus movement --save-state 100_percent
rommer launch-agent --project medabots-rpg --agent static --focus collision
rommer launch-agent --project medabots-rpg --agent refactor --stage type_resolver
rommer nuke --project medabots-rpg [--node node_001] [--force]
```

Each command is a module in `cli/commands/` with a `handler(args)` function. The CLI entry point routes to handlers. The backend REST API wraps the same handlers.

### Command: init-project

1. Extracts ZIP to temp directory
2. Spawns a Claude agent to classify files:
   - ROM file → `rom/`
   - Images → `knowledge/maps/`
   - PDFs → `knowledge/guides/`
   - Text files → `knowledge/guides/` or `knowledge/misc/`
   - Save files (.sav, .xps, .ss0) → `save_states/`
   - Code files (.xml with AR codes) → `knowledge/codes/`
3. Creates `project.json` with metadata
4. Initializes empty DB with base schema
5. Validates resources (iterative, agent-driven):
   - ROM loads in emulator → hard fail if not
   - Save files: attempt load. If format incompatible, agent iterates to convert
     (e.g., .xps → .sav, AR format → raw SRAM). Flags unconvertible files for
     human review in UI.
   - AR/CodeBreaker/GameShark codes: agent attempts to parse each format,
     tries decryption if encrypted (AR v3), validates decoded addresses against
     live emulator state. Flags unparseable codes for human review.
   - On validation failure: resource is flagged as `status: needs_review` in DB,
     not silently dropped. UI shows flagged resources for human verification.
6. Parses validated codes → injects as golden discoveries in DB
7. Scaffolds `src/CLAUDE.md` with platform-specific RE instructions

### Command: build-graph

1. Checks token count of walkthrough
2. If < 1M tokens: single Opus call for each pass (no chunking)
3. If > 1M tokens: chunk by section (current behavior)
4. Runs passes 1-4 sequentially
5. Runs pass 5 (augment): tags + knowledge linking
6. Stores results in DB

### Command: ghidra-decompile

1. Creates Ghidra project
2. Imports ROM with correct platform settings (GBA: ARM:LE:32:v4t, base 0x08000000)
3. Adds memory regions (IWRAM, EWRAM, VRAM, IO, OAM for GBA)
4. Runs auto-analysis
5. Exports golden discoveries as Ghidra labels
6. Imports labels into Ghidra project
7. Decompiles all functions → `src/functions/`
8. Exports combined `all_functions.c`, `function_index.json`, `label_xrefs.json`
9. Generates `src/CLAUDE.md` with known memory map + struct definitions

### Command: launch-agent

```
rommer launch-agent --project medabots-rpg --agent dynamic \
  --focus movement --save-state 100_percent --parallel 3
```

1. Resolves project paths
2. Instantiates agent class (DynamicAnalyzer, StaticAnalyzer, etc.)
3. Builds context from DB (discoveries, knowledge, tags)
4. Calls agent.spawn() which runs claude -p in background
5. On completion, calls agent.complete() which pushes findings to scratch DB

---

## 3. Agent Architecture

### 3.1 Base Agent

```python
class BaseAgent:
    def __init__(self, project, focus=None):
        self.project = project      # Project workspace paths
        self.db = project.get_db()  # Discovery DB connection
        self.focus = focus          # Optional focus area

    def build_context(self) -> str:
        """Build prompt context from DB + knowledge."""
        raise NotImplementedError

    def spawn(self) -> None:
        """Launch the agent (claude -p in background)."""
        context = self.build_context()
        # ... invoke claude CLI

    def complete(self, result: dict) -> None:
        """Process agent output, push discoveries to scratch."""
        candidates = result.get("candidates", [])
        for c in candidates:
            self.db.propose_discovery(c, source=self.agent_type)

    @property
    def agent_type(self) -> str:
        raise NotImplementedError
```

### 3.2 Dynamic Analyzer

- Inherits BaseAgent
- Spawns emulator server + claude -p with explore prompt
- Context includes: known addresses, relevant knowledge for focus area, save state
- On complete: pushes candidates + systems.json to DB/workspace

### 3.3 Static Analyzer

- Inherits BaseAgent
- Reads decompiled function files + xref map
- Context includes: priority functions, known structs, knowledge base
- On complete: renamed/annotated files, proposed discoveries, updated headers

### 3.4 Refactor Agents (sequential pipeline)

Each inherits BaseAgent, runs as a stage:

1. **TypeResolver** — Creates ghidra_types.h, fixes undefined4/byte/uint across all files
2. **LiteralPoolResolver** — Reads ROM binary at DAT_ addresses, resolves to actual values
3. **ForwardDeclGenerator** — Scans call graph, generates function prototypes
4. **StructAnnotator** — Rewrites pointer arithmetic to struct field access
5. **SystemTracer** — Documents complete systems, proposes new discoveries
6. **CodebaseReconstructor** (gated: requires >50% RE coverage) — Final stage that
   transforms the function-per-file decompiled output into a production-like C codebase:
   - Groups related functions into semantic modules (movement.c, combat.c, medals.c, etc.)
   - Creates a main.c with the game loop
   - Builds proper header hierarchy with forward declarations
   - Replaces raw address constants with named defines/struct access throughout
   - Adds a Makefile/build system targeting ARM7TDMI
   - Goal: byte-matching recompilation of the original ROM

---

## 4. Preprocessor Pipeline (Revised)

### Pass 1: Structure Detection (unchanged)
- Input: walkthrough text
- Output: section map (types, line ranges)

### Pass 2: System Audit + Schema (unchanged)
- Input: walkthrough + section map
- Output: game systems, proposed DB schema

### Pass 3: Data Extraction (unchanged)
- Input: walkthrough + schema
- Output: populated tables (items, NPCs, stats)

### Pass 4: Graph Generation (updated)
- Uses Opus 1M context — single call if walkthrough fits
- Includes tags in node output (no separate pass 4b)
- Output: nodes with tags, edges, discovery hints

### Pass 5: Augmentation (new, replaces pass4b)
- Links knowledge to nodes:
  - Map images matched by area/room name
  - AR codes matched by relevant system
  - Guide excerpts matched by game event
- Knowledge verified during init-project (saves load, codes parse)
- Golden discoveries from AR codes already in DB — linked to nodes by system relevance
- Output: knowledge_links table populated, nodes enriched

---

## 5. Knowledge Integration

Knowledge is grounded to nodes. Each node is an instanced context with specific knowledge attached.

### At init-project time:
- AR codes → parsed, validated, injected as golden discoveries
- Save states → validated (load in emulator)
- Maps → cataloged with area names
- Guides → indexed by section

### At augmentation (pass 5) time:
- Each node gets linked to relevant:
  - Map image(s) for its area
  - Golden discoveries relevant to its systems/tags
  - Guide excerpts for its game event

### At agent spawn time:
- Agent context builder pulls node's linked knowledge
- Dynamic agent sees: "This room's map shows a door at the north wall. Golden addresses for this area: player_x, room_id, collision_map..."
- Static agent sees: "Functions referencing room_id (12 xrefs). Trigger table format: 8-byte entries..."

---

## 6. Database Schema Updates

```sql
-- Knowledge resource tracking
CREATE TABLE knowledge_resource (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES project(id),
    type TEXT NOT NULL,          -- 'map', 'guide', 'codes', 'save', 'misc'
    filename TEXT NOT NULL,
    path TEXT NOT NULL,           -- relative to project workspace
    description TEXT,
    metadata TEXT                 -- JSON: dimensions, page count, code count, etc.
);

-- Knowledge linked to nodes
CREATE TABLE node_knowledge (
    id INTEGER PRIMARY KEY,
    node_id TEXT NOT NULL,
    resource_id INTEGER REFERENCES knowledge_resource(id),
    relevance TEXT,               -- why this resource is relevant
    context_snippet TEXT           -- extracted text/description to inject in prompt
);

-- Discovery source tracking (static vs dynamic vs codebreaker)
ALTER TABLE discovery ADD COLUMN source TEXT DEFAULT 'dynamic';
-- values: 'dynamic', 'static', 'codebreaker', 'manual'
```

---

## 7. Future: Graph Traversal with RL

Once sufficient RE is achieved (collision system decoded, entity table mapped, navigation working):

1. Build a game-specific navigator from discovered systems
2. Use the navigator + graph to attempt automated traversal
3. RL controller learns: given current game state + node goal → which navigator actions to take
4. Each successful node traversal creates a verified save state chain
5. The save states enable targeted RE at any point in the game

This is a long-term goal. Prerequisites:
- Collision map reading at runtime
- NPC interaction automation
- Room transition handling
- Dialogue advancement
- Menu navigation

---

## 8. Migration Plan

### Phase 1: Workspace separation
- [ ] Introduce ROMMER_PROJECTS_ROOT env var
- [ ] Create Project class that manages workspace paths
- [ ] Move game-specific data out of the repo to workspace
- [ ] Update config.py to resolve paths from workspace

### Phase 2: CLI refactor
- [ ] Create cli/ module with command/handler pattern
- [ ] Port existing scripts (nuke, record-playthrough) to CLI commands
- [ ] Add init-project command
- [ ] Add build-graph command (wraps existing pipeline)
- [ ] Add ghidra-decompile command
- [ ] Add launch-agent command

### Phase 3: Agent OOP refactor
- [ ] Create BaseAgent with spawn()/complete()
- [ ] Port explore_agent.py → agents/dynamic_analyzer.py
- [ ] Port static analysis agent → agents/static_analyzer.py
- [ ] Implement context builder that pulls knowledge + discoveries

### Phase 4: Preprocessor updates
- [ ] Update pass 4 to include tags in node output
- [ ] Replace pass 4b with pass 5 (augmentation + knowledge linking)
- [ ] Add single-call mode for Opus 1M context
- [ ] Add knowledge_resource and node_knowledge tables

### Phase 5: Ghidra integration cleanup
- [ ] Move Ghidra scripts to static_analysis/ghidra_scripts/
- [ ] Create ghidra-decompile CLI command
- [ ] Auto-setup GBA memory map (ROM base, IWRAM, EWRAM)
- [ ] Export labels from DB automatically

### Phase 6: Frontend updates
- [ ] Update web UI to reflect new workspace structure
- [ ] Add agent monitoring (spawn, status, results)
- [ ] Add knowledge browser
- [ ] Add discovery DB viewer with source filtering

---

## 9. Design Patterns

- **Command/Handler** — CLI commands. Each command is a module with a handler function. REST API wraps same handlers.
- **Strategy/Abstraction** — Emulator layer. BaseEmulator defines the interface, GBA/mGBA implements it. New platforms add new implementations.
- **Template Method** — BaseAgent defines spawn/complete lifecycle, subclasses implement build_context and processing logic.
- **Pipeline** — Preprocessor passes. Each pass transforms input and feeds the next.
- **Observer** — Discovery DB as shared state. Agents write discoveries, orchestrator watches for new entries and routes tasks.

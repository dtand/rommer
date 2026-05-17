# Rommer

AI-driven reverse engineering platform for GBA ROMs. Takes a game ROM + supplementary resources (walkthroughs, cheat codes, maps) and systematically decompiles, analyzes, and reconstructs the game's source code using AI agents.

## Quick Start

```bash
# Setup
cd ~/Projects/rommer
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # Edit with your paths

# Start services
./scripts/dev.sh  # Starts backend (8000), worker daemon, frontend (5174)

# Open UI
open http://localhost:5174
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 15+
- Ghidra 12.0+ (for decompilation)
- mGBA (for dynamic analysis)
- Claude CLI (`claude` command available)

## Pipeline

### Phase 1: Project Setup

```bash
# Option A: Upload via web UI (recommended)
# Go to http://localhost:5174, upload a ZIP with ROM + resources

# Option B: CLI
rommer init-project --name my-game --platform gba --zip ~/game-resources.zip
```

**What happens:**
1. AI agent classifies files (ROM, walkthroughs, maps, codes, saves)
2. ROM header validated (title, developer, region, checksum)
3. Files organized into project workspace at `~/.rommer/projects/{name}/`

### Phase 2: Schema Generation (automatic after upload)

Runs passes 1-3 on the primary walkthrough (blocking):

1. **Pass 1 — Structure Detection**: Identifies walkthrough sections
2. **Pass 2 — System Audit**: Identifies game systems (combat, movement, inventory, etc.)
3. **Pass 3 — Data Extraction**: Extracts game data tables (items, characters, locations)

Output: Game brief generated at `src/game_brief.md`

### Phase 3: Background Jobs (automatic after schema)

Three jobs kick off in parallel:

```bash
# Or manually:
rommer build-graph --project my-game           # Walkthrough → node DAG
rommer knowledge-analysis --project my-game    # Analyze resources for memory addresses
rommer ghidra-decompile --project my-game      # Decompile ROM → 16K+ C functions
```

**Graph Generation**: Converts walkthrough into a DAG of game events (200+ nodes)

**Knowledge Analysis**: AI agent reads cheat codes, guides, manuals. Extracts memory addresses as discoveries (golden/scratch). Supports `--parallel 3` for multiple agents with union merge.

**Ghidra Decompile**: Headless Ghidra imports ROM at 0x08000000, adds GBA memory regions, imports discovery labels, decompiles all functions to individual `.c` files.

### Phase 4: Code Preprocessing

```bash
rommer preprocess --project my-game
```

Deterministic scripts (no AI, instant):
1. **Type Resolution**: `undefined4` → `u32`, `byte` → `u8` (237K replacements)
2. **Literal Pool Resolution**: Reads ROM at DAT_ offsets, adds value comments
3. **Forward Declarations**: Generates `functions.h` with all prototypes
4. **Game Brief Refresh**: Updates `game_brief.md` with latest data

### Phase 5: Build Call Tree

```bash
rommer build-tree --project my-game
```

Builds function call graph from decompiled code:
- Parses caller/callee relationships
- Computes call tree levels (leaves = level 0)
- Augments with discovery references via literal pool resolution
- Augments with GBA IO register access patterns
- Output: `call_graph.json`

### Phase 6: Code Cleanup

```bash
rommer cleanup --project my-game --num-nodes 20 --parallel 5
```

AI agents clean Ghidra decompilation artifacts:
- Remove `in_lr`, `in_rX` register variables
- Replace `CONCAT*`, `SUB*`, `CARRY4`, `SBORROW` with standard C
- Replace `DAT_` references with resolved values
- Replace IO register DAT_ with named GBA registers
- Walks the call tree bottom-up, parallelized per level

### Phase 7: Static Analysis

```bash
rommer static-analyze --project my-game --num-nodes 20 --parallel 5
```

Bottom-up function analysis using AI:
- Level 0 (leaves): Classify and name simple functions
- Level 1+: Each function gets child summaries + game brief context
- Outputs: function name, system, confidence, completeness, description
- Results stored in `function_analysis` table + header comments in `.c` files
- Supports resume — skips already-analyzed functions

### Phase 8: Dynamic Analysis (optional)

```bash
# Launch emulator
rommer emulator --project my-game --save-state 100_percent.ss0

# Run exploration agents
# Via API: POST /api/jobs/dynamic-analysis with parallel support
```

AI agents explore the game via emulator TCP commands:
- Memory snapshots + diffs to find state changes
- Value scanning for known quantities
- Write-back verification of discovered addresses
- Reports discoveries as scratch tier

## Project Workspace

```
~/.rommer/projects/{name}/
├── project.json          # Metadata (title, platform, ROM info)
├── rom/game.gba          # The ROM file
├── knowledge/            # Supplementary resources
│   ├── guides/           # Walkthroughs
│   ├── maps/             # Area map images
│   ├── codes/            # Cheat code files
│   └── misc/             # Other reference material
├── save_states/          # Emulator save states
├── graph/                # Walkthrough graph data
│   ├── nodes/
│   └── preprocessor_output/
├── db/rommer.db          # SQLite database (legacy)
├── src/                  # Decompiled source code
│   ├── functions/        # Individual .c files per function
│   ├── all_functions.c   # Combined output
│   ├── function_index.json
│   ├── call_graph.json   # Function call tree
│   ├── game_brief.md     # Condensed game context
│   ├── literal_pool_map.json
│   └── include/          # Headers (ghidra_types.h, functions.h)
└── ghidra/               # Ghidra project files
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Web UI      │     │  FastAPI      │     │  Worker      │
│  React/Vite  │◄───►│  Backend      │     │  Daemon      │
│  :5174       │     │  :8000        │     │              │
└─────────────┘     └──────┬───────┘     └──────┬───────┘
                           │                     │
                    ┌──────▼─────────────────────▼──────┐
                    │           PostgreSQL               │
                    │  projects, discoveries, jobs,      │
                    │  function_analysis, events         │
                    │  LISTEN/NOTIFY for real-time       │
                    └───────────────────────────────────┘
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `rommer init-project --name X --zip Y` | Create project from ZIP |
| `rommer build-graph --project X` | Generate walkthrough graph |
| `rommer build-tree --project X` | Build function call tree |
| `rommer build-brief --project X` | Generate game brief |
| `rommer preprocess --project X` | Deterministic code cleanup |
| `rommer cleanup --project X` | AI code cleanup (Ghidra artifacts) |
| `rommer static-analyze --project X` | Bottom-up function analysis |
| `rommer ghidra-decompile --project X` | Decompile ROM via Ghidra |
| `rommer emulator --project X` | Launch mGBA (GUI or headless) |
| `rommer worker start` | Start job worker daemon |
| `rommer nuke --project X --force` | Delete project data |

## Agent Types

| Agent | Purpose | Parallel |
|-------|---------|----------|
| Knowledge Analysis | Parse resources for memory addresses | Yes (merge) |
| Dynamic Analysis | Emulator-based memory exploration | Yes (unique ports) |
| Code Cleanup | Remove Ghidra artifacts from code | Yes (per level) |
| Function Analysis | Name, classify, document functions | Yes (per level) |
| System Tracer | Trace complete game systems | No |

## Environment Variables

See `.env.example`:
```
DATABASE_URL=postgresql://localhost/rommer
ROMMER_PROJECTS_ROOT=~/.rommer/projects
MGBA_PATH=~/Desktop/ROMS/mGBA.app
MGBA_LIB_PATH=/tmp/mgba-src/build
GHIDRA_HEADLESS=/Applications/ghidra_12.0_PUBLIC/support/analyzeHeadless
```

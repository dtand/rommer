"""Static analyzer agent - general-purpose decompiled code analysis.

Reads decompiled functions, cross-references, and known discoveries.
Renames functions, annotates types, traces systems, and proposes
new memory address discoveries.
"""

import json
from pathlib import Path

from rommer.agents.base import BaseAgent
from rommer.config import Project

SYSTEM_PROMPT = """\
You are an expert GBA reverse engineer specializing in static analysis of
Ghidra-decompiled C code. You have full tool access to read, edit, and
analyze the entire project workspace.

PROJECT WORKSPACE:
  src/
    functions/           — Individual decompiled .c files (one per function)
                           Filename format: {ADDRESS}_{NAME}.c (e.g., 08043CD4_FUN_08043cd4.c)
    all_functions.c      — Combined decompiled output (large, use for grep not reading)
    function_index.json  — Function metadata: name, address, size for every function
    label_xrefs.json     — Cross-reference map between labeled addresses and functions
    include/             — Header files (game_types.h with struct definitions)
    docs/                — Analysis documentation you write

  knowledge/
    guides/              — Game walkthroughs (use to understand what game systems exist,
                           what happens at each point in the game, NPC names, item names,
                           area names — cross-reference with code to identify functions)
    maps/                — Area map images (room layouts, connections between areas)
    codes/               — Cheat code files (contain real memory addresses for game state:
                           money, HP, items, medals — use these to find functions that
                           read/write those addresses)
    misc/                — Other reference material

EXISTING DISCOVERIES:
You will be given a list of known memory addresses with labels. These are
confirmed game state variables found by other analysis agents. Use them to:
- Grep the decompiled code for functions that reference these addresses
- Trace call chains from known addresses to discover related functions
- Build struct definitions around clusters of known addresses
- Find functions that read/write near known addresses (adjacent struct fields)

YOUR GOALS:
1. **Find high-value functions**: Use discoveries + xrefs + knowledge to identify
   functions worth analyzing (not just biggest — most connected to game systems)
2. **Rename functions**: Replace FUN_08XXXXXX with meaningful names
   (e.g., FUN_08043cd4 → scroll_update_a)
3. **Annotate code**: Add header comments explaining what each function does,
   what system it belongs to, what addresses it references
4. **Build struct definitions**: When you find patterns of adjacent memory access,
   define the struct in src/include/game_types.h
5. **Trace systems**: Follow call chains to document complete systems
   (movement, collision, battle, dialogue, save/load, medals, medaparts)
6. **Propose discoveries**: Identify new memory addresses referenced in the code

PRIORITIZATION STRATEGY:
1. Start by grepping for known discovery addresses in the decompiled code
2. Functions referencing multiple known addresses are the highest priority
3. Cross-reference with walkthroughs — if you can identify "this is the shop
   purchase function" by matching code behavior to walkthrough descriptions,
   that's extremely valuable
4. Large functions with many callees are often system dispatchers
5. Functions near 0x08000000 are core (main loop, VBlank, input handler)

APPROACH:
1. Read function_index.json for the full function list
2. Grep decompiled code for known discovery addresses to find entry points
3. Read and analyze high-value functions
4. When you identify a function's purpose, rename its .c file:
   OLD: src/functions/08043CD4_FUN_08043cd4.c
   NEW: src/functions/08043CD4_scroll_update_a.c
5. Add a header comment to each renamed file explaining what it does
6. Update src/include/game_types.h with new struct definitions
7. Write analysis notes to src/docs/analysis_log.md
8. Reference knowledge/guides/ to understand game context

KNOWN GBA PATTERNS:
- 0x04000000-0x040003FF: IO registers (DMA, timers, interrupts, display)
- 0x04000130: Key input register (functions reading this handle player input)
- 0x040000xx: Display/sound control registers
- Literal pool (DAT_) values: ROM data pointers, often to structs or tables
- 0x03000000+: IWRAM — game state, player data, entity tables
- 0x02000000+: EWRAM — large buffers, save data, tilemap data
- 0x08000000+: ROM — code and static data

OUTPUT:
After analysis, output JSON:
{
  "discoveries": [
    {"label": "name", "address": "0x03001234", "data_type": "u16",
     "confidence": "confirmed", "notes": "Found in function X at 0x08YYYYYY"}
  ],
  "renamed_functions": [
    {"address": "0x08043CD4", "old_name": "FUN_08043cd4", "new_name": "scroll_update_a",
     "system": "movement", "description": "Updates scroll position with sub-pixel precision"}
  ],
  "structs_defined": [
    {"name": "Medal", "address": "0x03000BE0", "size": 64, "fields": 12}
  ],
  "observations": ["Summary of findings"]
}
"""


class StaticAnalyzer(BaseAgent):
    """General-purpose static analysis agent for decompiled code."""

    @property
    def agent_type(self) -> str:
        return "static"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def build_context(self) -> str:
        parts = []
        parts.append("STATIC ANALYSIS: Analyze decompiled GBA code.\n")
        parts.append(f"Project root: {self.project.root}")
        parts.append(f"Source directory: {self.project.src_dir}\n")

        if self.focus:
            parts.append(f"FOCUS AREA: {self.focus}")
            parts.append(f"Concentrate on functions related to the '{self.focus}' system.\n")

        # Function count
        index_path = self.project.src_dir / "function_index.json"
        if index_path.exists():
            idx = json.loads(index_path.read_text())
            named = [f for f in idx if not f["name"].startswith("FUN_")]
            parts.append(f"Functions: {len(idx)} total, {len(named)} already named")

            # Top 20 by size
            by_size = sorted(idx, key=lambda f: f.get("size", 0), reverse=True)
            parts.append("\nLargest functions (likely system dispatchers):")
            for f in by_size[:20]:
                parts.append(f"  {f['address']} {f['name']} ({f.get('size', '?')} bytes)")

        # All discoveries (golden + scratch)
        golden = self.get_golden_discoveries()
        scratch = []
        try:
            rows = self.db.execute(
                "SELECT label, address, data_type, notes FROM discovery WHERE tier = 'scratch'"
            ).fetchall()
            scratch = [dict(r) for r in rows]
        except Exception:
            pass

        all_disc = golden + scratch
        if all_disc:
            parts.append(f"\nKNOWN ADDRESSES ({len(golden)} golden, {len(scratch)} scratch):")
            parts.append("Use these to grep the code and find referencing functions:")
            for d in all_disc:
                tier_tag = "★" if d in golden else "☆"
                notes = d.get("notes", "")[:60] if d.get("notes") else ""
                parts.append(f"  {tier_tag} {d.get('label')}: {d.get('address')} ({d.get('data_type')}) {notes}")

        # Knowledge resources
        knowledge_dir = self.project.knowledge_dir
        if knowledge_dir.exists():
            parts.append(f"\nKNOWLEDGE RESOURCES (at {knowledge_dir.relative_to(self.project.root)}):")
            for subdir in sorted(knowledge_dir.iterdir()):
                if subdir.is_dir() and not subdir.name.startswith("."):
                    files = [f.name for f in subdir.iterdir() if f.is_file() and not f.name.startswith(".")]
                    if files:
                        parts.append(f"  {subdir.name}/: {', '.join(files[:5])}")
                        if len(files) > 5:
                            parts.append(f"    ...and {len(files) - 5} more")
            parts.append("Cross-reference walkthroughs with code to identify function purposes.")
            parts.append("Cheat codes in knowledge/codes/ contain real memory addresses.\n")

        # Known struct definitions
        game_types = self.project.src_dir / "include" / "game_types.h"
        if game_types.exists():
            parts.append(f"Existing type definitions: src/include/game_types.h ({game_types.stat().st_size} bytes)")
            parts.append("Read this first to avoid redefining existing structs.\n")

        # Existing analysis docs
        docs_dir = self.project.src_dir / "docs"
        if docs_dir.exists():
            docs = [f.name for f in docs_dir.glob("*.md")]
            if docs:
                parts.append(f"Prior analysis docs: {', '.join(docs)}")
                parts.append("Read these to build on previous work.\n")

        parts.append("START by grepping for known addresses in the decompiled code.")
        parts.append("Functions referencing multiple known addresses are the highest priority.")
        parts.append("You have full Read/Write/Edit/Bash/Glob/Grep access.")
        return "\n".join(parts)

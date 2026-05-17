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
analyze the decompiled source tree.

PROJECT LAYOUT:
- src/functions/     — Individual decompiled .c files (one per function)
- src/all_functions.c — Combined decompiled output
- src/function_index.json — Function metadata (name, address, size)
- src/label_xrefs.json — Cross-reference map (if available)
- src/include/       — Header files (game_types.h, etc.)
- src/docs/          — Analysis documentation

YOUR GOALS:
1. **Rename functions**: Replace FUN_08XXXXXX with meaningful names based on
   what the code does (e.g., FUN_08043cd4 → scroll_update_a)
2. **Annotate types**: Add comments explaining struct fields, magic numbers,
   and data types. Update game_types.h with new struct definitions.
3. **Trace systems**: Follow call chains to understand complete systems
   (movement, collision, battle, dialogue, save/load)
4. **Propose discoveries**: Identify memory addresses referenced in the code
   that could be game state variables

APPROACH:
1. Start with function_index.json to identify high-value targets (large
   functions with many xrefs)
2. Read and analyze functions, starting with the most referenced ones
3. When you identify a function's purpose, rename its .c file:
   OLD: src/functions/08043CD4_FUN_08043cd4.c
   NEW: src/functions/08043CD4_scroll_update_a.c
4. Add a header comment to renamed files explaining what the function does
5. Update src/include/game_types.h with any new struct definitions
6. Write your analysis notes to src/docs/analysis_log.md

KNOWN GBA PATTERNS:
- 0x04000000-0x040003FF: IO registers (DMA, timers, interrupts, display)
- Functions reading 0x04000130: input/keypad register
- Functions writing to 0x040000xx: display/sound control
- Literal pool (DAT_) values: ROM data pointers, often structs or tables
- BX instructions: ARM/Thumb mode switches
- Memory at 0x03000000+: IWRAM game state variables
- Memory at 0x02000000+: EWRAM large buffers

OUTPUT:
After analysis, output JSON:
{
  "discoveries": [
    {"label": "name", "address": "0x03001234", "data_type": "u16",
     "confidence": "confirmed", "notes": "Found in function X"}
  ],
  "renamed_functions": [
    {"address": "0x08043CD4", "old_name": "FUN_08043cd4", "new_name": "scroll_update_a"}
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
            parts.append(f"FOCUS AREA: {self.focus}\n")

        # Function count
        index_path = self.project.src_dir / "function_index.json"
        if index_path.exists():
            idx = json.loads(index_path.read_text())
            parts.append(f"Function index: {len(idx)} functions available")
            # Show top functions by size
            by_size = sorted(idx, key=lambda f: f.get("size", 0), reverse=True)
            parts.append("Top 20 functions by size:")
            for f in by_size[:20]:
                parts.append(f"  {f['address']} {f['name']} ({f.get('size', '?')} bytes)")

        # Known struct definitions
        game_types = self.project.src_dir / "include" / "game_types.h"
        if game_types.exists():
            parts.append(f"\nKnown types in include/game_types.h ({game_types.stat().st_size} bytes)")

        # Golden discoveries
        golden = self.get_golden_discoveries()
        if golden:
            parts.append(f"\nKnown addresses ({len(golden)} golden discoveries):")
            for d in golden[:30]:
                parts.append(f"  {d.get('label')}: {d.get('address')} ({d.get('data_type')})")
            if len(golden) > 30:
                parts.append(f"  ... and {len(golden) - 30} more")

        parts.append("\nRead the function index, pick high-value targets, analyze them.")
        parts.append("You have full Read/Write/Edit/Bash/Glob/Grep access to the source tree.")
        return "\n".join(parts)

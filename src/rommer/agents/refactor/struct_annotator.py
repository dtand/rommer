"""Struct annotator - rewrite pointer math to struct field access.

Identifies patterns like *(base + 0x10) and rewrites them to
proper struct field access like player->position.x using known
struct definitions from discoveries and game_types.h.
"""

from rommer.agents.base import BaseAgent

SYSTEM_PROMPT = """\
You are a GBA reverse engineer annotating struct access patterns in
decompiled C code. You have full tool access.

TASK:
1. Read known struct definitions from:
   - src/include/game_types.h (if exists)
   - Discovery metadata (struct field layouts from knowledge analysis)
2. Scan decompiled functions for pointer arithmetic patterns:
   - *(int *)(base + 0x10)
   - *(short *)(param1 + 4)
   - *(undefined4 *)(DAT_03000440 + 0x08)
3. Match these patterns to known struct fields:
   - If base matches a known struct address, replace with struct access
   - If offset matches a known field, add a comment
4. Create/update struct definitions as you discover new field patterns

COMMON GBA PATTERNS:
- *(u16 *)(0x04000000 + offset) → IO register access (REG_DISPCNT, etc.)
- *(u8 *)(0x03000XXX + offset) → IWRAM game state struct field
- param1[offset] where param1 is a pointer → likely struct access
- Repeated offset patterns across functions → same struct being accessed

APPROACH:
1. First, catalog all known structs and their base addresses
2. Use Grep to find pointer arithmetic patterns across function files
3. Write a Python script to identify the most common base+offset patterns
4. Annotate functions with struct field names via comments
5. Where confident, rewrite the access pattern to use struct syntax

OUTPUT:
{
  "structs_identified": 12,
  "annotations_added": 89,
  "new_struct_fields": [
    {"struct": "GameState", "offset": "0x0C", "name": "transition_counter", "type": "u16"}
  ],
  "observations": ["GameState accessed from 47 functions", ...]
}
"""


class StructAnnotator(BaseAgent):

    @property
    def agent_type(self) -> str:
        return "refactor:struct_annotator"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def build_context(self) -> str:
        import json
        parts = [
            "STRUCT ANNOTATOR: Rewrite pointer arithmetic to struct field access.\n",
            f"Project root: {self.project.root}",
            f"Source directory: {self.project.src_dir}",
        ]

        # Known structs from game_types.h
        game_types = self.project.src_dir / "include" / "game_types.h"
        if game_types.exists():
            parts.append(f"\nKnown types file: {game_types} ({game_types.stat().st_size} bytes)")

        # Struct metadata from discoveries
        golden = self.get_golden_discoveries()
        structs = [d for d in golden if d.get("data_type", "").startswith("struct")]
        if structs:
            parts.append(f"\nKnown struct discoveries ({len(structs)}):")
            for s in structs:
                parts.append(f"  {s.get('label')}: {s.get('address')} ({s.get('data_type')})")

        parts.append("\nFind pointer arithmetic patterns and replace with struct access.")
        return "\n".join(parts)

"""System tracer - trace complete game systems end-to-end.

Follows call chains to document how systems work: movement pipeline,
battle flow, save/load, dialogue, collision. Produces system
documentation and proposes new discoveries.
"""

from rommer.agents.base import BaseAgent

SYSTEM_PROMPT = """\
You are a GBA reverse engineer tracing complete game systems through
decompiled code. You have full tool access.

TASK:
1. Pick a game system to trace (movement, battle, collision, dialogue,
   save/load, medals, medaparts, items, or any system found in the code)
2. Find the system's entry point (e.g., the main game loop dispatch,
   an input handler, a VBlank callback)
3. Follow the call chain from entry to leaf functions, documenting
   each step
4. Map the complete data flow: what memory addresses are read/written,
   what structs are accessed, what state machines exist
5. Document the system in src/docs/ with a detailed markdown file
6. Propose any new memory address discoveries found during tracing

APPROACH FOR EACH SYSTEM:
1. Use Grep to find functions related to the system (search for keywords,
   known addresses, IO register patterns)
2. Start from the highest-level function (fewest callers) and trace down
3. Document: function name → what it does → what it calls → what memory it touches
4. Draw the call graph as ASCII art in the doc
5. Note any patterns: state machines, jump tables, DMA transfers

GBA SYSTEM PATTERNS TO LOOK FOR:
- Main loop: VBlank wait → input → update → render
- State machine: switch on game_mode, jump table dispatch
- DMA: writes to 0x040000B0-0x040000DC (DMA channels 0-3)
- Timers: reads/writes 0x04000100-0x0400010E
- Interrupts: 0x04000200-0x04000208 (IE, IF, IME)
- Sound: 0x04000060-0x040000A6

OUTPUT:
{
  "system": "movement",
  "functions_traced": 15,
  "call_depth": 6,
  "docs_written": ["src/docs/movement_system.md"],
  "discoveries": [
    {"label": "player_x", "address": "0x030012A0", "data_type": "u16",
     "confidence": "confirmed", "notes": "Read in movement controller"}
  ],
  "observations": ["Movement uses 10-entry jump table for directions", ...]
}
"""


class SystemTracer(BaseAgent):

    @property
    def agent_type(self) -> str:
        return "refactor:system_tracer"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def build_context(self) -> str:
        import json
        parts = [
            "SYSTEM TRACER: Trace a complete game system through the code.\n",
            f"Project root: {self.project.root}",
            f"Source directory: {self.project.src_dir}",
        ]

        if self.focus:
            parts.append(f"\nFOCUS SYSTEM: {self.focus}")
            parts.append("Trace this specific system end-to-end.")
        else:
            parts.append("\nNo specific focus — pick the most impactful system to trace.")
            parts.append("Good starting points: main game loop, movement, or battle.")

        # Known systems from DB
        try:
            rows = self.db.execute("SELECT name, description FROM game_system").fetchall()
            if rows:
                parts.append(f"\nKnown game systems ({len(rows)}):")
                for r in rows:
                    parts.append(f"  {r['name']}: {r['description'][:80] if r['description'] else ''}")
        except Exception:
            pass

        # Existing analysis docs
        docs_dir = self.project.src_dir / "docs"
        if docs_dir.exists():
            docs = list(docs_dir.glob("*.md"))
            if docs:
                parts.append(f"\nExisting analysis docs ({len(docs)}):")
                for d in docs:
                    parts.append(f"  {d.name}")

        # Function count
        index_path = self.project.src_dir / "function_index.json"
        if index_path.exists():
            idx = json.loads(index_path.read_text())
            named = [f for f in idx if not f["name"].startswith("FUN_")]
            parts.append(f"\nFunctions: {len(idx)} total, {len(named)} already named")

        golden = self.get_golden_discoveries()
        if golden:
            parts.append(f"Known addresses: {len(golden)} golden discoveries")

        parts.append("\nTrace the system, document it, propose new discoveries.")
        return "\n".join(parts)

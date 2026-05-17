"""Function analyzer agent — analyzes a batch of decompiled functions.

Used by the bottom-up static analysis pipeline. Receives a chunk of
functions (with their .c file contents and child summaries) and returns
structured analysis for each.
"""

import json
from pathlib import Path

from rommer.agents.base import BaseAgent
from rommer.config import Project

SYSTEM_PROMPT = """\
You are an expert GBA reverse engineer analyzing decompiled C functions.
You will receive one or more functions to analyze. For each function:

1. **Name it**: Replace FUN_08XXXXXX with a meaningful name based on what it does
2. **Classify**: Which game system does it belong to? (movement, combat, medals,
   save_system, render, input, audio, dialogue, inventory, menu, room_transition, etc.)
3. **Describe**: What does the function do? (1-3 sentences)
4. **Rate confidence**: 0.0-1.0 how sure you are about the name/purpose
5. **Rate completeness**: 0.0-1.0 how much of the function you understand
6. **Note discoveries**: Any new memory addresses you identified

CONTEXT YOU HAVE:
- The function's decompiled C code (with types fixed and literal pool resolved)
- Child function summaries (what the functions it calls do)
- Known discoveries (memory addresses already identified)
- Game brief (what this game is, its systems, known data)

READING THE CODE:
- DAT_ comments show resolved values: `DAT_08043cd4 /* = 0x03000BE0 (IWRAM = medal_array) */`
- 0x03XXXXXX = IWRAM game state, 0x02XXXXXX = EWRAM buffers
- 0x04XXXXXX = IO registers, 0x08XXXXXX = ROM data/code pointers
- Functions calling many children are often dispatchers or system managers
- Small functions (< 20 lines) are often simple getters/setters/utilities

OUTPUT: JSON array with one entry per function analyzed:
[
  {
    "address": "0x0805DEA8",
    "name": "save_game_data",
    "system": "save_system",
    "confidence": 0.9,
    "completeness": 0.8,
    "description": "Serializes medals, medaparts, cash, items to save buffer",
    "notes": "Copies 16-byte header then iterates medal array",
    "discoveries": [
      {"label": "save_header_rom", "address": "0x08483C20", "data_type": "u8[16]",
       "confidence": "probable", "notes": "ROM data copied as first 16 bytes of save"}
    ]
  }
]

If a function is too small or trivial to name meaningfully (simple return, thunk,
single assignment), still classify it but set confidence/completeness to 1.0 and
name it descriptively (e.g., "return_zero", "thunk_to_08043cd4", "set_flag_0x10").
"""


class FunctionAnalyzer(BaseAgent):
    """Analyzes a batch of functions for the bottom-up pipeline."""

    def __init__(self, project: Project, functions: list[dict] | None = None, **kwargs):
        super().__init__(project, **kwargs)
        self.functions = functions or []

    @property
    def agent_type(self) -> str:
        return "function_analysis"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def build_context(self) -> str:
        parts = []

        # Game brief
        brief_path = self.project.src_dir / "game_brief.md"
        if brief_path.exists():
            parts.append(f"<game_brief>\n{brief_path.read_text()}\n</game_brief>\n")

        # Functions to analyze
        parts.append(f"Analyze these {len(self.functions)} functions:\n")

        for func in self.functions:
            parts.append(f"--- FUNCTION: {func['address']} ({func.get('original_name', '?')}) ---")

            # File content
            if func.get("code"):
                parts.append(func["code"])
            else:
                file_path = func.get("file_path")
                if file_path and Path(file_path).exists():
                    parts.append(Path(file_path).read_text())

            # Child summaries
            if func.get("child_summaries"):
                parts.append("\nChild functions (already analyzed):")
                for child in func["child_summaries"]:
                    parts.append(f"  {child['address']} {child['name']} ({child['system']}): {child.get('description', '')[:100]}")

            # Augmentation
            if func.get("discovery_refs"):
                refs = func["discovery_refs"]
                parts.append(f"\nDiscovery refs: {', '.join(r['label'] for r in refs)}")

            if func.get("io_registers"):
                parts.append(f"IO registers: {', '.join(func['io_registers'].values())}")

            parts.append("")

        parts.append("Output the JSON array with your analysis for each function.")
        return "\n".join(parts)

    def complete(self, result: dict | list) -> list[dict]:
        """Process results — update function_analysis table + discovery table."""
        if isinstance(result, str):
            return []

        # Handle both single dict and array
        analyses = result if isinstance(result, list) else result.get("functions", [result])

        staged = []
        for a in analyses:
            address = a.get("address", "")
            name = a.get("name", "")
            if not address:
                continue

            # Upsert function_analysis
            try:
                p = "%s" if hasattr(self.db, '_conn') else "?"
                project_id = self.db.execute("SELECT id FROM project LIMIT 1").fetchone()[0]

                # Check if exists
                existing = self.db.execute(
                    f"SELECT id FROM function_analysis WHERE project_id = {p} AND address = {p}",
                    (project_id, address),
                ).fetchone()

                if existing:
                    self.db.execute(
                        f"""UPDATE function_analysis SET
                            name = {p}, system = {p}, description = {p},
                            confidence = {p}, completeness = {p}, notes = {p},
                            analyzed_by = {p}, updated_at = CURRENT_TIMESTAMP
                            WHERE id = {p}""",
                        (name, a.get("system"), a.get("description"),
                         a.get("confidence", 0), a.get("completeness", 0),
                         a.get("notes"), self.agent_type, existing[0]),
                    )
                else:
                    self.db.execute(
                        f"""INSERT INTO function_analysis
                            (project_id, address, original_name, name, system, description,
                             confidence, completeness, level, notes, analyzed_by)
                            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})""",
                        (project_id, address, a.get("original_name", ""),
                         name, a.get("system"), a.get("description"),
                         a.get("confidence", 0), a.get("completeness", 0),
                         a.get("level"), a.get("notes"), self.agent_type),
                    )

                self.db.commit()
                staged.append(a)
            except Exception as e:
                print(f"Error saving analysis for {address}: {e}")

            # Insert discoveries
            for d in a.get("discoveries", []):
                d_addr = d.get("address", "")
                d_label = d.get("label", "")
                if d_addr and d_label:
                    try:
                        existing = self.db.execute(
                            f"SELECT id FROM discovery WHERE address = {p}",
                            (d_addr,),
                        ).fetchone()
                        if not existing:
                            self.db.execute(
                                f"""INSERT INTO discovery
                                    (label, address, data_type, tier, confidence,
                                     source, discovery_method, notes)
                                    VALUES ({p}, {p}, {p}, 'scratch', {p}, 'static_analysis', 'function_analyzer', {p})""",
                                (d_label, d_addr, d.get("data_type", "u32"),
                                 d.get("confidence", "probable"), d.get("notes", "")),
                            )
                            self.db.commit()
                    except Exception:
                        pass

        return staged

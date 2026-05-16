"""Knowledge analyzer agent - reviews all project resources for discoveries.

This agent iterates over each file in knowledge/, understands its content,
and extracts any useful information for reverse engineering. It has full
tool access so it can:
- Read files in any format
- Write Python helper scripts to parse binary/encoded data
- Run scripts to decode encrypted codes (AR v3, etc.)
- Extract memory addresses, game data structures, symbols
"""

import json
from pathlib import Path

from rommer.agents.base import BaseAgent
from rommer.config import Project

SYSTEM_PROMPT = """\
You are a GBA reverse engineering expert analyzing game knowledge resources.
You have full tool access — you can read files, write Python scripts, and run them.

Your workspace is the project directory. You are analyzing supplementary game
resources to extract anything useful for reverse engineering.

WHAT TO LOOK FOR:
- Memory addresses (hex values like 0x03001234)
- Cheat codes (CodeBreaker, Action Replay, GameShark) — these contain real memory addresses
- Game data structures (item tables, character stats, medapart data)
- Technical information about the game's internals
- Any symbols, labels, or named memory locations

HOW TO HANDLE DIFFERENT FILE TYPES:
- Plain text (.txt, .md): Read directly, scan for hex addresses and technical info
- Rich text (.rtf): Read and parse, extract meaningful content
- XML documents: May be Word XML — extract text content first, then analyze
- PDF files: Use Python to extract text if possible
- Code files (.xml with cheat codes): Parse the code format, decode if encrypted
- Images (.gif, .png): Note them as map resources but don't try to extract addresses

FOR CHEAT CODES:
- CodeBreaker unencrypted format: TTAAAAAA YYYY (T=type, A=address, Y=value)
  - Type 3: 16-bit write to IWRAM (0x03000000 + offset)
  - Type 8: 8-bit write to IWRAM
  - Type 0: 32-bit write to EWRAM (0x02000000 + offset)
- Action Replay v3: encrypted — write a Python decryption script if you recognize the format
- GameShark: similar to CodeBreaker but different encoding
- If codes appear encrypted (random-looking hex), try to identify the encryption
  and write a decryption script

STRUCT AND ARRAY ANALYSIS:
When you discover a struct or array, go deep:
- Identify the base address, stride (bytes per entry), and count
- Break down EVERY field within the struct with offset, type, and semantic name
- For arrays, map individual indices to their game meaning (e.g., index 0 = Kuwagata medal)
- Use cheat code labels to infer field meanings (e.g., "Max HP" code at offset +4 means field at +4 is HP)
- Cross-reference multiple codes targeting the same struct to build complete field maps

APPROACH:
1. List all files in the knowledge/ directory
2. Process each file one at a time
3. For complex files (encrypted codes, binary data), write a Python helper script,
   run it, and use the output
4. Collect all discovered addresses
5. For any discovered structs/arrays, analyze field layout in detail

OUTPUT FORMAT:
After analyzing ALL files, output a JSON object:
{
  "discoveries": [
    {
      "label": "descriptive_name",
      "address": "0x03001234",
      "data_type": "u16",
      "confidence": "confirmed",
      "notes": "Found via CodeBreaker code for 'Max Money'",
      "metadata": null
    },
    {
      "label": "medal_array",
      "address": "0x03000BE0",
      "data_type": "struct[30]",
      "confidence": "confirmed",
      "notes": "30-slot medal array, 0x40 bytes per entry",
      "metadata": {
        "kind": "array",
        "stride": 64,
        "count": 30,
        "fields": [
          {"offset": 0, "name": "id", "type": "u16", "notes": "medal type ID"},
          {"offset": 2, "name": "exp", "type": "u16"},
          {"offset": 4, "name": "attribute", "type": "u8", "values": {"0": "Speed", "1": "Power"}}
        ],
        "entries": [
          {"index": 0, "label": "Kuwagata"},
          {"index": 1, "label": "Kabuto"}
        ]
      }
    }
  ],
  "observations": [
    "Summary of what was found in each file"
  ]
}
"""


class KnowledgeAnalyzer(BaseAgent):
    """Analyzes all knowledge resources using full tool access.

    Unlike other agents, this one processes files autonomously —
    reading, writing helper scripts, and running them as needed.
    """

    @property
    def agent_type(self) -> str:
        return "knowledge_analysis"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def build_context(self) -> str:
        """Build context listing all knowledge files for the agent to process."""
        parts = []
        parts.append("Analyze the knowledge resources in this project.\n")
        parts.append(f"Project root: {self.project.root}\n")

        # List all knowledge files with sizes
        knowledge_dir = self.project.knowledge_dir
        if knowledge_dir.exists():
            parts.append("Files to analyze:")
            for f in sorted(knowledge_dir.rglob("*")):
                if f.is_file() and not f.name.startswith("."):
                    size = f.stat().st_size
                    size_str = f"{size / 1024:.0f}KB" if size > 1024 else f"{size}B"
                    rel = f.relative_to(self.project.root)
                    parts.append(f"  {rel} ({size_str})")

        # Include save states info
        saves_dir = self.project.save_states_dir
        if saves_dir.exists():
            save_files = [f.name for f in saves_dir.iterdir() if f.is_file()]
            if save_files:
                parts.append(f"\nSave states available: {', '.join(save_files)}")

        # Include existing golden discoveries so agent doesn't re-discover
        golden = self.get_golden_discoveries()
        if golden:
            parts.append(f"\nAlready known addresses ({len(golden)} golden discoveries) — do NOT re-discover:")
            for d in golden[:30]:
                parts.append(f"  {d.get('label')}: {d.get('address')} ({d.get('data_type')})")
            if len(golden) > 30:
                parts.append(f"  ... and {len(golden) - 30} more")

        parts.append("\nProcess each file. For code files, try to decode and extract real memory addresses.")
        parts.append("Write helper scripts if needed — you have full Bash/Read/Write/Edit/Glob/Grep access.")
        parts.append("Output your final JSON with all discoveries at the end.")

        return "\n".join(parts)

    def complete(self, result: dict) -> list[dict]:
        """Process agent output — insert discoveries into DB."""
        if isinstance(result, str):
            return []

        discoveries = result.get("discoveries", [])
        candidates = result.get("candidates", discoveries)

        staged = []
        for c in candidates:
            address = c.get("address", "")
            label = c.get("label", "")
            if not address or not label:
                continue

            # Check for duplicate
            existing = self.db.execute(
                "SELECT id FROM discovery WHERE address = ? AND label = ?",
                (address, label),
            ).fetchone()
            if existing:
                continue

            # Serialize metadata if present
            metadata = c.get("metadata")
            metadata_json = json.dumps(metadata) if metadata else None

            try:
                self.db.execute(
                    """INSERT INTO discovery
                       (label, address, data_type, tier, confidence,
                        source, discovery_method, notes, metadata)
                       VALUES (?, ?, ?, ?, ?, 'knowledge_analysis', 'agent', ?, ?)""",
                    (
                        label,
                        address,
                        c.get("data_type", "u16"),
                        "golden" if c.get("confidence") == "confirmed" else "scratch",
                        c.get("confidence", "probable"),
                        c.get("notes", ""),
                        metadata_json,
                    ),
                )
                staged.append(c)
            except Exception:
                pass

        if staged:
            self.db.commit()

        return staged

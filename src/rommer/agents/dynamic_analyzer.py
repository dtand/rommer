"""Dynamic analyzer agent - freeform RE exploration via emulator.

Launches an mGBA emulator server, then spawns a Claude agent that
sends commands over TCP to explore memory and discover addresses.
"""

import json
from pathlib import Path

from rommer.agents.base import BaseAgent
from rommer.config import Project

SYSTEM_PROMPT = """\
You are an expert GBA reverse engineer with access to a running mGBA emulator.
Your goal is to systematically discover memory addresses and data structures
by observing how memory changes in response to game inputs.

EMULATOR COMMANDS (send via: echo "<command>" | nc localhost {port}):

Input:
  press <keys...> [--frames N] [--wait N]   — press buttons (A B UP DOWN LEFT RIGHT START SELECT L R)
  run <count>                                 — advance N frames

Memory:
  read <0xADDR> [--size N] [--format hex|dec|ascii]  — read memory
  write <0xADDR> <value> [--width 8|16|32]           — write memory
  snapshot <name> [--region ewram|iwram]              — save memory region
  diff <snap_a> <snap_b> [--region ewram] [--limit N] — compare snapshots
  scan-value <value> [--width 8|16|32] [--region ewram] — find value in memory
  scan-ascii <text> [--region ewram|iwram]            — find ASCII string

State:
  savepoint <name>     — save full emulator state (instant restore)
  restore <name>       — restore a savepoint
  save <path>          — save state to file
  load <path>          — load state from file
  screenshot <path>    — capture frame to PNG

Info:
  info    — session status
  help    — list commands

METHODOLOGY:
1. Take a screenshot to see the current game state
2. Create a memory snapshot ("before")
3. Perform a game action (press buttons, advance frames)
4. Create another snapshot ("after")
5. Diff the snapshots to see what changed
6. Analyze the changes to identify meaningful addresses
7. Verify by writing values and observing effects

Use savepoints to create restore points before risky experiments.

TIPS:
- EWRAM (0x02000000): large buffers, save data, tilemap data
- IWRAM (0x03000000): game state, player data, entity tables
- Start with obvious things: move the player, open a menu, start a battle
- Use scan-value to find known values (money amount, HP, etc.)
- Use diff to find what changes during specific actions
- Write values to verify your discoveries (e.g., set money to 999)

OUTPUT:
After exploration, output JSON:
{{
  "discoveries": [
    {{
      "label": "player_x",
      "address": "0x030012A0",
      "data_type": "u16",
      "confidence": "confirmed",
      "notes": "Verified by write test — changing value moves player",
      "metadata": null
    }}
  ],
  "observations": ["Summary of what was explored and found"]
}}
"""


class DynamicAnalyzer(BaseAgent):
    """Freeform exploration agent using emulator + memory analysis."""

    def __init__(
        self,
        project: Project,
        focus: str | None = None,
        node_id: str | None = None,
        server_port: int = 9123,
        frame_budget: int = 50000,
        save_state: str | None = None,
    ):
        super().__init__(project, focus, node_id)
        self.server_port = server_port
        self.frame_budget = frame_budget
        self.save_state = save_state

    @property
    def agent_type(self) -> str:
        return "dynamic"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT.format(port=self.server_port)

    def build_context(self) -> str:
        parts = []
        parts.append(
            f"DYNAMIC ANALYSIS: Explore the game via emulator to discover memory addresses.\n\n"
            f"Emulator server: localhost:{self.server_port}\n"
            f"Send commands: echo \"<command>\" | nc localhost {self.server_port}\n"
            f"Frame budget: {self.frame_budget} frames\n"
        )

        if self.focus:
            parts.append(f"FOCUS AREA: {self.focus}")
            parts.append(f"Concentrate your exploration on the {self.focus} system.\n")

        # Known game systems
        try:
            rows = self.db.execute("SELECT name, description FROM game_system").fetchall()
            if rows:
                parts.append("Game systems to investigate:")
                for r in rows:
                    parts.append(f"  {r['name']}: {r['description'][:80] if r['description'] else ''}")
                parts.append("")
        except Exception:
            pass

        # Existing discoveries (don't re-discover)
        golden = self.get_golden_discoveries()
        if golden:
            parts.append(f"Already known addresses ({len(golden)} — do NOT re-discover):")
            for d in golden[:40]:
                parts.append(f"  {d.get('label')}: {d.get('address')} ({d.get('data_type')})")
            if len(golden) > 40:
                parts.append(f"  ... and {len(golden) - 40} more")
            parts.append("")

        parts.append(
            "Start by taking a screenshot to see the game state, then systematically "
            "explore. Use snapshots + diffs to find what changes. Verify discoveries "
            "by writing test values. Be thorough — you have plenty of frames."
        )

        return "\n".join(parts)

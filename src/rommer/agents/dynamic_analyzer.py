"""Dynamic analyzer agent - freeform RE exploration via emulator."""

import json
from pathlib import Path

from rommer.agents.base import BaseAgent
from rommer.agents.systems import (
    compute_relevant_systems,
    get_node_tags,
    get_predecessor_tags,
)
from rommer.config import Project

SYSTEM_PROMPT_TEMPLATE = """\
You are an expert GBA reverse engineer. You have access to a running mGBA emulator
via TCP commands. Your goal is to systematically discover memory addresses and
data structures by observing how memory changes in response to game inputs.

You can send commands to the emulator with:
  echo "<command>" | nc localhost {port}

Available commands: press, run_frames, read_u8, read_u16, read_u32, read_range,
write_u8, write_u16, write_u32, diff, snapshot, load_snapshot, screenshot, quit.

Output your findings as JSON with "result" and "candidates" keys.
Each candidate should have: label, address, data_type, before_value, after_value, confidence, method, reasoning.
"""

CORE_SYSTEM_DESCRIPTIONS = {
    "movement": "Player position, walking speed, tile-based grid movement.",
    "collision": "Collision map buffer, tile type values, map dimensions.",
    "camera": "Viewport following player. Camera X/Y addresses.",
    "npc_interaction": "NPC entity table: base address, struct size, fields.",
    "dialogue": "Text display system, dialogue active flag, text pointer.",
    "room_transitions": "Room/map ID, transition triggers, room loading.",
    "game_state": "Overall game mode (overworld/dialogue/menu/battle/cutscene).",
    "text_input": "Character entry cursor position, text buffer.",
    "navigation": "Multi-room area connections, warp tiles.",
    "overworld": "Town/outdoor map system, larger tile maps.",
    "save_system": "Save/load functionality, save data location.",
    "inventory": "Items, money counter, item list.",
    "purchase": "Shop transaction flow, buying items.",
    "combat": "Battle system, combatant data, HP/damage.",
}


class DynamicAnalyzer(BaseAgent):
    """Freeform exploration agent using emulator + memory analysis."""

    def __init__(
        self,
        project: Project,
        focus: str | None = None,
        node_id: str | None = None,
        server_port: int = 9123,
        frame_budget: int = 50000,
    ):
        super().__init__(project, focus, node_id)
        self.server_port = server_port
        self.frame_budget = frame_budget

    @property
    def agent_type(self) -> str:
        return "dynamic"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT_TEMPLATE.format(port=self.server_port)

    def build_context(self) -> str:
        """Build exploration prompt with knowledge, discoveries, and systems."""
        parts = []

        parts.append(
            f"EXPLORE mode{f' for node {self.node_id}' if self.node_id else ''}.\n"
            f"Freely explore the game environment. Your mission is to reverse-engineer "
            f"the game's memory systems.\n\n"
            f"Emulator server on port {self.server_port}.\n"
            f"Frame budget: {self.frame_budget} frames\n"
        )

        # Controls
        controls = self.get_controls_reference()
        if controls:
            parts.append(f"<controls>\n{controls}\n</controls>")

        # Relevant systems from tags
        if self.node_id:
            node_tags = get_node_tags(self.db, self.node_id)
            pred_tags = get_predecessor_tags(self.db, self.node_id)
            relevant = compute_relevant_systems(node_tags, pred_tags)

            if relevant:
                system_lines = []
                all_game_systems = self._get_game_systems()
                for name in relevant:
                    desc = CORE_SYSTEM_DESCRIPTIONS.get(name, "")
                    if name in all_game_systems:
                        desc = f"{desc} {all_game_systems[name]}" if desc else all_game_systems[name]
                    system_lines.append(f"- **{name}**: {desc}" if desc else f"- **{name}**")
                parts.append(
                    "<target_systems>\nFocus on these systems:\n"
                    + "\n".join(system_lines)
                    + "\n</target_systems>"
                )

            # Node tags for exploration hints
            if node_tags:
                parts.append(f"<node_tags>\nTags: {', '.join(node_tags)}\n</node_tags>")

        # Golden discoveries (known addresses)
        golden = self.get_golden_discoveries()
        if golden:
            parts.append(
                "<known_addresses>\nAlready discovered (do not re-discover):\n"
                + json.dumps(golden[:50], indent=2)
                + "\n</known_addresses>"
            )

        parts.append(
            f"\nBegin exploration. You have {self.frame_budget} frames. "
            f"Be thorough and systematic."
        )

        return "\n\n".join(parts)

    def _get_game_systems(self) -> dict[str, str]:
        """Get game system descriptions from DB."""
        try:
            rows = self.db.execute("SELECT name, description FROM game_system").fetchall()
            return {r["name"]: r["description"] for r in rows}
        except Exception:
            return {}

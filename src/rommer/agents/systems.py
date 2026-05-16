"""Tag-driven system computation.

Maps node tags to relevant game systems, replacing manual SYSTEM_UNLOCKS
with a data-driven mapping.
"""

import json
import sqlite3

TAG_TO_SYSTEMS = {
    "npc_dialogue": ["dialogue", "npc_interaction"],
    "story_trigger": ["dialogue", "game_state"],
    "room_change": ["room_transitions", "collision"],
    "item_receive": ["inventory"],
    "item_use": ["inventory"],
    "money_decrease": ["inventory"],
    "money_increase": ["inventory"],
    "shop_transaction": ["inventory", "purchase"],
    "combat_start": ["combat"],
    "combat_reward": ["combat", "inventory"],
    "menu_interaction": ["game_state"],
    "text_input": ["text_input"],
    "save_prompt": ["save_system"],
    "indoor_navigation": ["movement", "collision", "camera"],
    "outdoor_navigation": ["movement", "collision", "camera", "overworld"],
    "multi_screen_travel": ["movement", "collision", "camera", "navigation"],
    "single_room": ["movement", "collision"],
    "boss_battle": ["combat"],
    "random_battle": ["combat"],
    "first_combat": ["combat", "abilities", "medals_and_medaforce"],
    "first_shop": ["inventory", "purchase"],
    "first_npc_interaction": ["dialogue", "npc_interaction"],
    "position_change": ["movement"],
    "flag_change": ["game_state"],
    "new_entity_loaded": ["npc_interaction"],
    "map_load": ["room_transitions"],
    "dialogue_state_change": ["dialogue"],
    "inventory_mutation": ["inventory"],
    "stat_change": ["combat"],
}

CORE_SYSTEMS = {"movement", "collision", "camera", "game_state"}


def compute_relevant_systems(
    node_tags: list[str],
    predecessor_tags: list[str] | None = None,
) -> list[str]:
    """Derive relevant game systems from a node's tags and predecessors'."""
    systems = set(CORE_SYSTEMS)
    all_tags = list(node_tags) + (predecessor_tags or [])
    for tag in all_tags:
        base_tag = tag.split(":")[0]
        systems.update(TAG_TO_SYSTEMS.get(base_tag, []))
    return sorted(systems)


def get_predecessor_tags(conn: sqlite3.Connection, node_id: str) -> list[str]:
    """Collect tags from all predecessor nodes by order_index."""
    try:
        row = conn.execute(
            "SELECT order_index FROM graph_node WHERE node_id = ?", (node_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return []
    if not row:
        return []

    order_idx = row["order_index"] or 0
    rows = conn.execute(
        "SELECT tags FROM graph_node WHERE order_index < ? AND tags IS NOT NULL",
        (order_idx,),
    ).fetchall()

    all_tags = []
    for r in rows:
        try:
            tags = json.loads(r["tags"])
            all_tags.extend(tags)
        except (json.JSONDecodeError, TypeError):
            pass
    return all_tags


def get_node_tags(conn: sqlite3.Connection, node_id: str) -> list[str]:
    """Get tags for a specific node."""
    try:
        row = conn.execute(
            "SELECT tags FROM graph_node WHERE node_id = ?", (node_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return []
    if not row or not row["tags"]:
        return []
    try:
        return json.loads(row["tags"])
    except (json.JSONDecodeError, TypeError):
        return []

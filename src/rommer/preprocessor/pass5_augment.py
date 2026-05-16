"""Pass 5: Augmentation - tagging + knowledge linking.

Assigns tags to untagged nodes and links knowledge resources to nodes
based on area/system/event relevance.
"""

import json
import sqlite3

from rommer.config import Project
from rommer.preprocessor.claude import invoke

TAG_TAXONOMY = """
Event tags: npc_dialogue, story_trigger, room_change, item_receive, item_use,
  money_decrease, money_increase, shop_transaction, combat_start, combat_reward,
  menu_interaction, text_input, save_prompt
Context tags: indoor_navigation, outdoor_navigation, multi_screen_travel,
  single_room, first_X (first_combat, first_shop, first_npc_interaction)
Entity tags: named_npc:NAME, boss_battle, random_battle, medabot:NAME
RE tags: position_change, flag_change, new_entity_loaded, map_load,
  dialogue_state_change, inventory_mutation, stat_change
"""


def augment_nodes(project: Project, model: str = "sonnet") -> dict:
    """Run augmentation: tag untagged nodes + link knowledge.

    Returns summary dict with counts.
    """
    conn = project.get_db()

    # Tag untagged nodes
    tagged_count = _tag_untagged_nodes(conn, project, model)

    # Link knowledge resources to nodes
    links_created = _link_knowledge(conn, project)

    conn.close()
    return {"tagged_count": tagged_count, "links_created": links_created}


def _tag_untagged_nodes(conn: sqlite3.Connection, project: Project, model: str) -> int:
    """Assign tags to nodes that don't have them yet."""
    try:
        nodes = conn.execute(
            "SELECT node_id, title, description, goal, action_type, section_ref "
            "FROM graph_node WHERE tags IS NULL OR tags = '[]' ORDER BY order_index"
        ).fetchall()
    except sqlite3.OperationalError:
        return 0

    if not nodes:
        return 0

    system_prompt = (
        "You are a game analyst assigning tags to graph nodes.\n"
        f"Tag taxonomy:\n{TAG_TAXONOMY}\n\n"
        "Output ONLY JSON: {\"tags\": [\"tag1\", \"tag2\", ...]}"
    )

    tagged = 0
    for node in nodes:
        prompt = (
            f"Assign 1-8 tags to this node:\n"
            f"Title: {node['title']}\n"
            f"Description: {node['description']}\n"
            f"Action: {node['action_type']}\n"
            f"Goal: {node['goal']}\n"
        )

        result = invoke(prompt=prompt, system_prompt=system_prompt, model=model, timeout=120)
        if isinstance(result, dict) and "tags" in result:
            conn.execute(
                "UPDATE graph_node SET tags = ? WHERE node_id = ?",
                (json.dumps(result["tags"]), node["node_id"]),
            )
            conn.commit()
            tagged += 1

    return tagged


def _link_knowledge(conn: sqlite3.Connection, project: Project) -> int:
    """Link knowledge resources to relevant nodes."""
    # Check if knowledge_resource table exists and has entries
    try:
        resources = conn.execute("SELECT * FROM knowledge_resource").fetchall()
    except sqlite3.OperationalError:
        return 0

    if not resources:
        # Catalog knowledge files if not yet done
        resources = _catalog_knowledge(conn, project)

    if not resources:
        return 0

    # Link resources to nodes by type
    links = 0
    try:
        nodes = conn.execute("SELECT node_id, tags, section_ref FROM graph_node").fetchall()
    except sqlite3.OperationalError:
        return 0

    for resource in resources:
        res_type = resource["type"] if isinstance(resource, sqlite3.Row) else resource.get("type")
        res_id = resource["id"] if isinstance(resource, sqlite3.Row) else resource.get("id")

        # Maps link to nodes with room_change/navigation tags
        if res_type == "map":
            for node in nodes:
                tags = json.loads(node["tags"]) if node["tags"] else []
                if any(t in tags for t in ["room_change", "indoor_navigation", "outdoor_navigation", "map_load"]):
                    conn.execute(
                        "INSERT INTO node_knowledge (node_id, resource_id, relevance) VALUES (?, ?, ?)",
                        (node["node_id"], res_id, "map for navigation context"),
                    )
                    links += 1

    if links:
        conn.commit()
    return links


def _catalog_knowledge(conn: sqlite3.Connection, project: Project) -> list:
    """Scan knowledge directory and catalog resources in DB."""
    knowledge_dir = project.knowledge_dir
    if not knowledge_dir.exists():
        return []

    entries = []
    type_map = {
        "maps": "map",
        "guides": "guide",
        "codes": "codes",
        "saves": "save",
        "misc": "misc",
    }

    for subdir, res_type in type_map.items():
        sub = knowledge_dir / subdir
        if not sub.exists():
            continue
        for f in sub.iterdir():
            if f.is_file():
                conn.execute(
                    "INSERT INTO knowledge_resource (type, filename, path) VALUES (?, ?, ?)",
                    (res_type, f.name, str(f.relative_to(project.root))),
                )
                entries.append({"type": res_type, "filename": f.name})

    if entries:
        conn.commit()

    return conn.execute("SELECT * FROM knowledge_resource").fetchall()

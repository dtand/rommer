"""Pass 4: Graph Generation - create walkthrough node DAG."""

from pathlib import Path

from rommer.preprocessor.claude import invoke


TAG_TAXONOMY = """\
Event tags: npc_dialogue, story_trigger, room_change, item_receive, item_use,
  money_decrease, money_increase, shop_transaction, combat_start, combat_reward,
  menu_interaction, text_input, save_prompt
Context tags: indoor_navigation, outdoor_navigation, multi_screen_travel,
  single_room, first_X (e.g. first_combat, first_shop, first_npc_interaction)
Entity tags: named_npc:NAME, boss_battle, random_battle
RE tags: position_change, flag_change, new_entity_loaded, map_load,
  dialogue_state_change, inventory_mutation, stat_change
"""


def _build_prompts(walkthrough_path: Path, section_map: dict, systems: dict) -> tuple[str, str]:
    """Build system prompt and user prompt for graph generation."""
    system_prompt = (
        "You are converting a game walkthrough into a directed acyclic graph (DAG) of "
        "exploration nodes for reverse engineering purposes. Each node represents ONE "
        "discrete player action that could be completed in a short play session "
        "(30 seconds to 2 minutes of gameplay).\n\n"
        "GRANULARITY RULES:\n"
        "- Mirror the guide as closely as possible — break it into succinct, actionable steps\n"
        "- If the guide says 'go left, talk to NPC, pick up item', that's 3 separate nodes\n"
        "- Each room transition is its own node\n"
        "- Each NPC conversation is its own node\n"
        "- Each item pickup/purchase is its own node\n"
        "- Each battle is its own node\n"
        "- Navigation between areas should be broken into individual movement steps\n"
        "- A full walkthrough should produce hundreds of nodes\n\n"
        "Each node must be independently verifiable — an agent with an emulator should be able "
        "to execute just that one step and confirm success via memory state changes.\n\n"
        f"TAG TAXONOMY (assign 1-8 tags per node):\n{TAG_TAXONOMY}\n"
        "Use snake_case for all tags. Prefix entity tags (named_npc:dr_aki, medabot:rokusho).\n"
        "Mark first_X for the first occurrence of each mechanic.\n\n"
        "Output JSON only."
    )

    # Output file path — agent writes JSON here since output may be too large for stdout
    output_file = walkthrough_path.parent.parent.parent / "graph" / "preprocessor_output" / "pass4_graph_output.json"

    prompt = (
        f"Read the walkthrough at: {walkthrough_path}\n\n"
        f"Section map: {section_map}\n"
        f"Game systems: {[s.get('name') for s in systems.get('game_systems', [])]}\n\n"
        "Generate the graph. For each node provide:\n"
        "- node_id: short snake_case identifier (e.g. 'enter_lab', 'talk_dr_aki')\n"
        "- name: brief action description\n"
        "- title: section reference + short title (e.g. '3.1a - Talk to Dr. Aki')\n"
        "- description: what the player does (1-2 sentences)\n"
        "- section_ref: which walkthrough section this belongs to\n"
        "- goal: what the player is trying to achieve\n"
        "- success_criteria: how to verify completion (memory state change)\n"
        "- action_type: one of [navigation, dialogue, combat, acquisition, menu, cutscene, puzzle]\n"
        "- order_index: sequential integer (1, 2, 3...)\n"
        "- estimated_inputs: button sequence to execute this step\n"
        "- discovery_hints: what memory addresses might change during this step\n"
        "- tags: 1-8 tags from the taxonomy\n\n"
        "For edges: connect each node to its immediate successor(s).\n"
        "Format: {\"from\": \"node_id_a\", \"to\": \"node_id_b\"}\n\n"
        "CRITICAL: The output will be large (200+ nodes). Do NOT describe the output — "
        "write the complete JSON object to this file:\n"
        f"  {output_file}\n\n"
        "Use the Write tool to write the FULL JSON: {{\"nodes\": [...], \"edges\": [...]}}\n"
        "After writing the file, respond with just: DONE"
    )

    return system_prompt, prompt


def _read_output_file(walkthrough_path: Path) -> dict | None:
    """Read the graph JSON written by the agent to the output file."""
    import json
    output_file = walkthrough_path.parent.parent.parent / "graph" / "preprocessor_output" / "pass4_graph_output.json"
    if output_file.exists():
        try:
            data = json.loads(output_file.read_text())
            if isinstance(data, dict) and "nodes" in data:
                output_file.unlink()  # Clean up
                return data
        except (json.JSONDecodeError, Exception):
            pass
    return None


def generate_graph(
    model: str, walkthrough_path: Path, section_map: dict, systems: dict, data: dict
) -> dict:
    """Generate the walkthrough graph (nodes + edges).

    The agent writes output to a file (too large for stdout).
    """
    system_prompt, prompt = _build_prompts(walkthrough_path, section_map, systems)

    invoke(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        allowed_tools=["Read", "Write"],
        add_dirs=[walkthrough_path.parent, walkthrough_path.parent.parent.parent / "graph"],
        timeout=1800,
    )

    # Read from file the agent wrote
    result = _read_output_file(walkthrough_path)
    if result:
        return result
    return {"nodes": [], "edges": [], "error": "Agent did not write output file"}


def generate_graph_streaming(
    model: str, walkthrough_path: Path, section_map: dict, systems: dict, data: dict,
    on_event=None,
) -> dict:
    """Generate graph with streaming output for live logging."""
    from rommer.preprocessor.claude import invoke_streaming

    system_prompt, prompt = _build_prompts(walkthrough_path, section_map, systems)

    invoke_streaming(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        allowed_tools=["Read", "Write"],
        add_dirs=[walkthrough_path.parent, walkthrough_path.parent.parent.parent / "graph"],
        timeout=1800,
        on_event=on_event,
    )

    # Read from file the agent wrote
    result = _read_output_file(walkthrough_path)
    if result:
        return result
    return {"nodes": [], "edges": [], "error": "Agent did not write output file"}


def generate_graph_streaming(
    model: str, walkthrough_path: Path, section_map: dict, systems: dict, data: dict,
    on_event=None,
) -> dict:
    """Generate graph with streaming output for live logging.

    Same as generate_graph but uses invoke_streaming with on_event callback.
    """
    from rommer.preprocessor.claude import invoke_streaming

    system_prompt, prompt = _build_prompts(walkthrough_path, section_map, systems)

    result = invoke_streaming(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        allowed_tools=["Read"],
        add_dirs=[walkthrough_path.parent],
        timeout=1800,
        on_event=on_event,
    )

    if isinstance(result, dict):
        return result
    return {"nodes": [], "edges": [], "raw": str(result)[:500]}

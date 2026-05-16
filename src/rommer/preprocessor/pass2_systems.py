"""Pass 2: System Audit - identify game systems and propose schema."""

from pathlib import Path

from rommer.preprocessor.claude import invoke


def audit_systems(model: str, walkthrough_path: Path, section_map: dict) -> dict:
    """Analyze walkthrough for game systems and propose DB schema.

    Returns game systems list and proposed SQL schema.
    """
    system_prompt = (
        "You are analyzing a game walkthrough to identify all game systems "
        "(combat, inventory, movement, dialogue, etc.) and propose a database schema "
        "for storing extracted game data. Output JSON."
    )

    prompt = (
        f"Read the walkthrough at: {walkthrough_path}\n\n"
        f"Section map: {section_map}\n\n"
        "Identify all game systems. For each:\n"
        "- name (slug)\n"
        "- description\n"
        "- table_names (proposed DB tables)\n\n"
        "Also propose control mappings (button -> action by context).\n\n"
        "Output: {\"game_systems\": [...], \"control_mappings\": [...], \"schema_sql\": \"...\"}"
    )

    result = invoke(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        allowed_tools=["Read"],
        add_dirs=[walkthrough_path.parent],
    )

    if isinstance(result, dict):
        return result
    return {"game_systems": [], "raw": str(result)[:500]}

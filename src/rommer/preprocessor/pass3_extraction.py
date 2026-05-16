"""Pass 3: Data Extraction - extract structured data from walkthrough."""

from pathlib import Path

from rommer.preprocessor.claude import invoke


def extract_data(model: str, walkthrough_path: Path, section_map: dict, systems: dict) -> dict:
    """Extract structured game data from walkthrough text.

    Returns populated data tables.
    """
    system_prompt = (
        "You are extracting structured game data from a walkthrough. "
        "Use the proposed schema to populate tables with items, NPCs, stats, etc. "
        "Output JSON with a 'tables' key mapping table names to row arrays."
    )

    prompt = (
        f"Read the walkthrough at: {walkthrough_path}\n\n"
        f"Section map: {section_map}\n"
        f"Game systems: {systems.get('game_systems', [])}\n\n"
        "Extract all game data into tables. Output: {\"tables\": {\"table_name\": [...rows]}}"
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
    return {"tables": {}, "raw": str(result)[:500]}

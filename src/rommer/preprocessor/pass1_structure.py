"""Pass 1: Structure Detection - identify sections in walkthrough text."""

from pathlib import Path

from rommer.preprocessor.claude import invoke


def detect_structure(model: str, walkthrough_path: Path) -> dict:
    """Analyze walkthrough document structure.

    Returns section map with types and line ranges.
    """
    system_prompt = (
        "You are analyzing a game walkthrough document. Identify all major sections, "
        "their types (narrative, reference, systems, items, maps), and line ranges. "
        "Output JSON with a 'sections' array."
    )

    prompt = (
        f"Read the walkthrough at: {walkthrough_path}\n\n"
        "Identify all major sections. For each section provide:\n"
        "- section_id (slug)\n"
        "- title\n"
        "- type (narrative|reference|systems|items|maps)\n"
        "- line_start, line_end\n"
        "- description (1 sentence)\n\n"
        "Output as JSON: {\"sections\": [...]}"
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
    return {"sections": [], "raw": str(result)[:500]}

"""Pass 4: Graph Generation - create walkthrough node DAG."""

from pathlib import Path

from rommer.preprocessor.claude import invoke


def generate_graph(
    model: str, walkthrough_path: Path, section_map: dict, systems: dict, data: dict
) -> dict:
    """Generate the walkthrough graph (nodes + edges).

    Returns nodes array and edges array with tags included.
    """
    system_prompt = (
        "You are converting a game walkthrough into a directed acyclic graph (DAG) of "
        "exploration nodes. Each node represents a discrete game action or event that "
        "can be independently verified. Include tags for each node. Output JSON."
    )

    prompt = (
        f"Read the walkthrough at: {walkthrough_path}\n\n"
        f"Section map: {section_map}\n"
        f"Systems: {systems.get('game_systems', [])}\n\n"
        "Generate graph nodes and edges. Each node needs:\n"
        "- node_id, name, title, description, section_ref\n"
        "- goal, success_criteria, action_type\n"
        "- order_index, estimated_inputs, discovery_hints\n"
        "- tags (1-8 tags from taxonomy)\n\n"
        "Output: {\"nodes\": [...], \"edges\": [...]}"
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
    return {"nodes": [], "edges": [], "raw": str(result)[:500]}

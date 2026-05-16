"""Knowledge analyzer agent - reviews supplementary resources for discoveries."""

import json
from pathlib import Path

from rommer.agents.base import BaseAgent
from rommer.config import Project

SYSTEM_PROMPT = """\
You are a GBA reverse engineer analyzing supplementary game resources.
Review the provided files and extract any information that could help with
memory address discovery:

- Hex addresses mentioned in guides or notes
- Memory values referenced in cheat descriptions
- Data structure hints (struct sizes, field offsets)
- Technical information about game internals

Output JSON with "candidates" array. Each candidate:
{label, address, data_type, confidence, method: "knowledge_analysis", reasoning}

Only include entries where you can identify a specific memory address.
If no addresses are found, return {"candidates": []}.
"""


class KnowledgeAnalyzer(BaseAgent):
    """Analyzes supplementary knowledge resources for potential discoveries."""

    @property
    def agent_type(self) -> str:
        return "knowledge_analysis"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def build_context(self) -> str:
        """Build context from all non-walkthrough knowledge resources."""
        parts = []
        parts.append("Analyze these game resources for memory addresses and technical info:\n")

        knowledge_dir = self.project.knowledge_dir
        if not knowledge_dir.exists():
            return "No knowledge resources found."

        # Read text-based resources (skip binary/images)
        text_extensions = {".txt", ".md", ".rtf", ".csv", ".xml", ".json", ".cht"}

        for f in sorted(knowledge_dir.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix.lower() not in text_extensions:
                continue
            # Skip the primary walkthrough (already used for graph)
            if "walkthrough_1" in f.name.lower() or f.name == "walkthrough.txt":
                continue

            try:
                content = f.read_text(errors="replace")
                # Truncate very large files
                if len(content) > 50000:
                    content = content[:50000] + "\n...[truncated]"
                parts.append(f"\n--- {f.name} ---\n{content}")
            except Exception:
                continue

        # Include known golden discoveries for context
        golden = self.get_golden_discoveries()
        if golden:
            parts.append(
                "\n--- Already known addresses (do not re-discover) ---\n"
                + json.dumps(golden[:50], indent=2)
            )

        return "\n".join(parts)

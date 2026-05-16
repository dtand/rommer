"""Static analyzer agent - decompiled code annotation and xref tracing."""

import json
from pathlib import Path

from rommer.agents.base import BaseAgent
from rommer.config import Project

SYSTEM_PROMPT = """\
You are an expert GBA reverse engineer specializing in static analysis of
decompiled C code. You have access to Ghidra-decompiled functions, cross-references,
and known memory addresses from dynamic analysis.

Your goals:
1. Rename functions and variables to meaningful names
2. Annotate struct fields and type definitions
3. Trace cross-references to understand system interactions
4. Propose new memory address discoveries based on code analysis

Output your findings as JSON with "result" and "candidates" keys.
Each candidate: {label, address, data_type, confidence, method, reasoning}
"""


class StaticAnalyzer(BaseAgent):
    """Static analysis agent working on decompiled code."""

    def __init__(
        self,
        project: Project,
        focus: str | None = None,
        node_id: str | None = None,
    ):
        super().__init__(project, focus, node_id)

    @property
    def agent_type(self) -> str:
        return "static"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def build_context(self) -> str:
        """Build context with decompiled code, xrefs, and known addresses."""
        parts = []

        parts.append(
            "STATIC ANALYSIS mode.\n"
            "Analyze decompiled GBA code to understand game systems.\n"
        )

        if self.focus:
            parts.append(f"Focus area: {self.focus}\n")

        # Known struct definitions
        include_dir = self.project.src_dir / "include"
        game_types = include_dir / "game_types.h"
        if game_types.exists():
            parts.append(
                f"<known_types>\n{game_types.read_text()}\n</known_types>"
            )

        # Golden discoveries for cross-referencing
        golden = self.get_golden_discoveries()
        if golden:
            parts.append(
                "<known_addresses>\n"
                + json.dumps(golden[:100], indent=2)
                + "\n</known_addresses>"
            )

        # Priority functions (if available)
        priority_path = self.project.src_dir / "priority_functions.json"
        if priority_path.exists():
            parts.append(
                f"<priority_functions>\n{priority_path.read_text()}\n</priority_functions>"
            )

        # Xref map (if available)
        xref_path = self.project.src_dir / "label_xrefs.json"
        if xref_path.exists():
            xrefs = json.loads(xref_path.read_text())
            # Only include xrefs relevant to focus
            if self.focus:
                relevant = {k: v for k, v in xrefs.items() if self.focus.lower() in k.lower()}
                if relevant:
                    parts.append(
                        f"<relevant_xrefs>\n{json.dumps(relevant, indent=2)}\n</relevant_xrefs>"
                    )
            else:
                parts.append(f"<xref_count>\n{len(xrefs)} cross-references available\n</xref_count>")

        parts.append(
            "\nAnalyze the code. Rename functions, annotate types, "
            "and propose new memory address discoveries."
        )

        return "\n\n".join(parts)

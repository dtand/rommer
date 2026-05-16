"""Struct annotator - rewrite pointer math to struct field access."""

from rommer.agents.base import BaseAgent


class StructAnnotator(BaseAgent):
    """Rewrites pointer arithmetic to struct field access patterns."""

    @property
    def agent_type(self) -> str:
        return "refactor:struct_annotator"

    def get_system_prompt(self) -> str:
        return (
            "You are a GBA reverse engineer annotating struct access patterns. "
            "Replace raw pointer arithmetic (*(base + 0x10)) with proper struct "
            "field access (player->position.x) using known struct definitions."
        )

    def build_context(self) -> str:
        # TODO: Full implementation in follow-up
        return (
            "STRUCT ANNOTATOR stage.\n"
            f"Source: {self.project.src_dir}\n"
            "Rewrite pointer arithmetic to struct field access."
        )

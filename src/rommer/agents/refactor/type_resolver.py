"""Type resolver - fix Ghidra undefined4/byte/uint types across decompiled code."""

from rommer.agents.base import BaseAgent


class TypeResolver(BaseAgent):
    """Creates ghidra_types.h and fixes undefined types across all files."""

    @property
    def agent_type(self) -> str:
        return "refactor:type_resolver"

    def get_system_prompt(self) -> str:
        return (
            "You are a GBA reverse engineer fixing Ghidra's generic type names. "
            "Replace undefined4, undefined2, undefined1, byte, uint with proper "
            "GBA types (u32, u16, u8, s32, etc.) based on usage context."
        )

    def build_context(self) -> str:
        # TODO: Full implementation in follow-up
        return (
            "TYPE RESOLVER stage.\n"
            f"Source directory: {self.project.src_dir}\n"
            "Fix Ghidra type names across all decompiled functions."
        )

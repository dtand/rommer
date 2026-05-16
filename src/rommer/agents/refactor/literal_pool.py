"""Literal pool resolver - resolve DAT_ references from ROM binary."""

from rommer.agents.base import BaseAgent


class LiteralPoolResolver(BaseAgent):
    """Reads ROM binary at DAT_ addresses, resolves to actual values."""

    @property
    def agent_type(self) -> str:
        return "refactor:literal_pool"

    def get_system_prompt(self) -> str:
        return (
            "You are a GBA reverse engineer resolving literal pool references. "
            "DAT_ labels in Ghidra output refer to ROM data. Read the ROM binary "
            "at those offsets and replace with actual constant values or pointers."
        )

    def build_context(self) -> str:
        # TODO: Full implementation in follow-up
        return (
            "LITERAL POOL RESOLVER stage.\n"
            f"ROM: {self.project.rom_path}\n"
            f"Source: {self.project.src_dir}\n"
            "Resolve DAT_ references to actual values from ROM binary."
        )

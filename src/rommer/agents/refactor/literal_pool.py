"""Literal pool resolver - resolve DAT_ references from ROM binary.

Ghidra labels ROM data as DAT_08XXXXXX. This agent reads the actual
ROM bytes at those offsets and replaces DAT_ labels with meaningful
values (constants, string pointers, function pointers, struct pointers).
"""

from rommer.agents.base import BaseAgent

SYSTEM_PROMPT = """\
You are a GBA reverse engineer resolving Ghidra's literal pool references.
You have full tool access including Bash to run Python scripts.

BACKGROUND:
In ARM/Thumb code, constants too large for immediate encoding are stored
in a "literal pool" near the function. Ghidra labels these as DAT_08XXXXXX.
The actual value at that ROM address tells you what the code is really
referencing.

TASK:
1. Find all DAT_ references in the decompiled functions
2. For each DAT_ address, read the ROM binary at that offset to get
   the actual 4-byte value stored there
3. Interpret the value:
   - 0x08XXXXXX → pointer to another ROM function/data (look it up)
   - 0x03XXXXXX → pointer to IWRAM game state variable
   - 0x02XXXXXX → pointer to EWRAM buffer
   - 0x04XXXXXX → IO register address
   - 0x05/06/07XXXXXX → Palette/VRAM/OAM pointer
   - Small values (< 0x10000) → likely a constant
4. Replace the DAT_ label in the code with the resolved value or a
   meaningful name
5. Create a resolved_literals.json mapping DAT_ → value

APPROACH:
Write a Python script that:
1. Reads the ROM binary
2. Scans function files for DAT_08XXXXXX patterns
3. Reads the 4 bytes at ROM offset (address - 0x08000000)
4. Outputs a mapping of DAT_ address → resolved value

Then use the mapping to annotate the decompiled functions with comments.

OUTPUT:
{
  "resolved_count": 1234,
  "pointers_to_rom": 456,
  "pointers_to_iwram": 78,
  "pointers_to_ewram": 23,
  "constants": 677,
  "observations": ["Common pattern: DAT_ used for jump tables", ...]
}
"""


class LiteralPoolResolver(BaseAgent):

    @property
    def agent_type(self) -> str:
        return "refactor:literal_pool"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def build_context(self) -> str:
        parts = [
            "LITERAL POOL RESOLVER: Resolve DAT_ references from ROM binary.\n",
            f"Project root: {self.project.root}",
            f"ROM path: {self.project.rom_path}",
            f"Source directory: {self.project.src_dir}",
        ]

        if self.project.rom_path.exists():
            size = self.project.rom_path.stat().st_size
            parts.append(f"ROM size: {size} bytes ({size / 1024 / 1024:.1f} MB)")

        funcs_dir = self.project.src_dir / "functions"
        if funcs_dir.exists():
            parts.append(f"Function files: {len(list(funcs_dir.glob('*.c')))}")

        parts.append("\nWrite a Python script to read the ROM and resolve DAT_ references.")
        parts.append("The ROM is loaded at 0x08000000, so offset = address - 0x08000000.")
        return "\n".join(parts)

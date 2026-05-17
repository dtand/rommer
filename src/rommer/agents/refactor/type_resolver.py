"""Type resolver - fix Ghidra's generic types across decompiled code.

Replaces undefined4, undefined2, undefined1, byte, uint with proper
GBA types (u32, u16, u8, s32, etc.) based on usage context.
Creates/updates a ghidra_types.h header with GBA-standard typedefs.
"""

from rommer.agents.base import BaseAgent

SYSTEM_PROMPT = """\
You are a GBA reverse engineer fixing Ghidra's generic type names in
decompiled C code. You have full tool access.

TASK:
1. Create src/include/ghidra_types.h with GBA-standard type definitions:
   typedef unsigned char u8;
   typedef unsigned short u16;
   typedef unsigned int u32;
   typedef signed char s8;
   typedef signed short s16;
   typedef signed int s32;
   typedef volatile u16 vu16;
   typedef volatile u32 vu32;
   // GBA-specific
   typedef u32 bool32;
   #define TRUE 1
   #define FALSE 0
   #define NULL ((void*)0)

2. Scan decompiled functions for Ghidra's generic types:
   - undefined4 → u32 (or s32 if used in signed comparisons)
   - undefined2 → u16 (or s16)
   - undefined1 → u8 (or s8 or bool)
   - undefined → u8
   - byte → u8
   - uint → u32
   - ushort → u16
   - ulong → u32
   - longlong → s64

3. Use context to choose the right replacement:
   - Compared against negative values → signed (s32, s16, s8)
   - Used as array index → u32 or int
   - Bitwise operations → unsigned (u32, u16, u8)
   - Boolean checks (== 0, != 0) → bool or u8
   - Pointer arithmetic → u32 or void*
   - Written to IO registers → vu16, vu32

4. Apply changes using Edit tool across the function files.
   Focus on the most impactful files first (large functions, many xrefs).

OUTPUT:
{
  "files_modified": 42,
  "replacements": {"undefined4": 230, "undefined2": 89, "byte": 156},
  "observations": ["Most undefined4 are u32", "Found s16 pattern in battle code"]
}
"""


class TypeResolver(BaseAgent):

    @property
    def agent_type(self) -> str:
        return "refactor:type_resolver"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def build_context(self) -> str:
        parts = [
            "TYPE RESOLVER: Fix Ghidra's generic types across decompiled functions.\n",
            f"Project root: {self.project.root}",
            f"Source directory: {self.project.src_dir}",
            f"Functions directory: {self.project.src_dir / 'functions'}",
        ]

        # Count files and sample for type usage
        funcs_dir = self.project.src_dir / "functions"
        if funcs_dir.exists():
            c_files = list(funcs_dir.glob("*.c"))
            parts.append(f"\n{len(c_files)} function files to process.")
            parts.append("Use Grep to find files with undefined4, byte, uint, etc.")
            parts.append("Start with the most common patterns, apply bulk fixes.")

        return "\n".join(parts)

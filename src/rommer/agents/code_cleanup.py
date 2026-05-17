"""Code cleanup agent — removes Ghidra decompilation artifacts.

Walk 0 of the bottom-up pipeline. Cleans up Ghidra-specific constructs
in decompiled C code before the analysis agents see it.
"""

import json
from pathlib import Path

from rommer.agents.base import BaseAgent
from rommer.config import Project

SYSTEM_PROMPT = """\
You are cleaning up Ghidra-decompiled GBA C code. Your job is to transform
Ghidra's non-standard C output into clean, readable C while preserving
the exact logic and semantics.

You will receive function files to clean up. For each function, rewrite
the code fixing ALL of the following artifacts:

GHIDRA REGISTER VARIABLES:
- `in_lr` — This is the ARM link register (return address). Remove the
  declaration and any usage. If used in calculations, it's likely a
  decompilation error — replace with 0 or remove the expression.
- `in_r0`, `in_r1`, `in_r2`, `in_r3` — These are ARM register params
  that Ghidra couldn't properly map. Rename to param_1, param_2, etc.
  or merge with existing params if they correspond.
- `extraout_r1`, `extraout_r1_00`, etc. — Ghidra modeling functions that
  return values in multiple registers. Usually the secondary return value
  from division or 64-bit operations. Replace with proper variable or
  remove if unused.

GHIDRA MACROS (replace with standard C):
- `CONCAT44(a, b)` → `((u64)(a) << 32) | (u32)(b)` (concat two 32-bit to 64-bit)
- `CONCAT22(a, b)` → `((u32)(a) << 16) | (u16)(b)`
- `CONCAT11(a, b)` → `((u16)(a) << 8) | (u8)(b)`
- `CONCAT12(a, b)` → similar byte concatenation
- Other CONCAT variants: `CONCATxy(a, b)` → shift `a` left by `y*8` bits, OR with `b`
- `SUB41(a, 0)` → `(u8)(a)` (extract low byte from 32-bit)
- `SUB42(a, 0)` → `(u16)(a)` (extract low halfword)
- `SUB21(a, 0)` → `(u8)(a)` (extract low byte from 16-bit)
- `SUB81(a, 0)` → `(u8)(a)` (extract byte from 64-bit)
- Other SUB variants: `SUBxy(a, n)` → extract `x` bytes starting at byte `n`
- `CARRY4(a, b)` → `((u32)a + (u32)b < (u32)a)` (unsigned overflow check)
- `SBORROW4(a, b)` → signed overflow check for subtraction
- `ZEXT14(x)` → `(u32)(u8)(x)` (zero-extend byte to 32-bit)
- `ZEXT24(x)` → `(u32)(u16)(x)` (zero-extend halfword to 32-bit)
- `SEXT14(x)` → `(s32)(s8)(x)` (sign-extend byte to 32-bit)
- `SEXT24(x)` → `(s32)(s16)(x)`

DAT_ REFERENCES:
- If a comment shows the resolved value: `DAT_0805df84 /* = 0x03002B70 (IWRAM = cash) */`
  Replace with the actual value: `*(u32*)0x03002B70` or a meaningful name if labeled
- For ROM pointers: `DAT_08XXXXXX /* = 0x08YYYYYY (ROM pointer) */` → `(void*)0x08YYYYYY`
- For unresolved DAT_ without comments: leave as-is
- For IO registers: `DAT_04000130` → `REG_KEYINPUT` (use standard GBA register names)

GBA IO REGISTER NAMES:
- DAT_04000000 → REG_DISPCNT
- DAT_04000004 → REG_DISPSTAT
- DAT_04000006 → REG_VCOUNT
- DAT_04000130 → REG_KEYINPUT
- DAT_040000XX → use standard GBA register name if known
- DAT_040000B0-DC → REG_DMAx (DMA registers)

OTHER CLEANUP:
- Remove `(void)0;` statements (Ghidra artifacts)
- Clean up redundant casts: `(u32)(u32)x` → `(u32)x`
- Fix parameter types where obvious from context
- Look for any other Ghidra-specific artifacts and clean them up

IMPORTANT RULES:
- Do NOT change the logic or control flow
- Do NOT rename functions (that's a later pass)
- Do NOT add comments explaining the code (that's also later)
- ONLY clean up Ghidra artifacts into standard C
- Preserve the exact semantics — the cleaned code must do the same thing

SYNTAX VERIFICATION:
After cleaning each function, you MUST verify it passes a syntax check.
For each cleaned function, write it to a temp file and run:

  gcc -fsyntax-only -std=c99 -w -include {include_dir}/ghidra_types.h <file>

- Use -w to suppress warnings (we only care about errors)
- If it fails, read the error, fix the code, and re-verify
- Common fixes: add missing declarations, fix cast syntax, add missing semicolons
- Functions may reference undefined symbols (other functions, globals) — that's OK,
  those will cause "undeclared" errors which you should ignore. Focus on syntax errors
  from YOUR transformations (bad casts, missing parens, etc.)
- If a function still has syntax errors after 2 fix attempts, output it as-is
  with a note about the remaining error

OUTPUT: JSON array with one entry per function:
[
  {{
    "address": "0x08001FF8",
    "cleaned_code": "// Function: FUN_08001ff8\\n// Address: 0x08001FF8\\n...",
    "syntax_ok": true
  }}
]
"""


class CodeCleanupAgent(BaseAgent):
    """Cleans Ghidra artifacts from a batch of decompiled functions."""

    def __init__(self, project: Project, functions: list[dict] | None = None, **kwargs):
        super().__init__(project, **kwargs)
        self.functions = functions or []

    @property
    def agent_type(self) -> str:
        return "code_cleanup"

    def get_system_prompt(self) -> str:
        include_dir = self.project.src_dir / "include"
        return SYSTEM_PROMPT.format(include_dir=include_dir)

    def build_context(self) -> str:
        parts = []
        parts.append(f"Clean up these {len(self.functions)} Ghidra-decompiled functions:")
        parts.append(f"Include directory for syntax check: {self.project.src_dir / 'include'}\n")

        for func in self.functions:
            parts.append(f"--- FUNCTION: {func['address']} ---")
            if func.get("code"):
                parts.append(func["code"])
            elif func.get("file_path") and Path(func["file_path"]).exists():
                parts.append(Path(func["file_path"]).read_text())
            parts.append("")

        parts.append("Output the JSON array with cleaned code for each function.")
        return "\n".join(parts)

"""Forward declaration generator - generate function prototypes from call graph.

Scans decompiled functions for cross-references, builds a call graph,
and generates header files with proper function prototypes and forward
declarations.
"""

from rommer.agents.base import BaseAgent

SYSTEM_PROMPT = """\
You are a GBA reverse engineer generating forward declarations and
function prototypes. You have full tool access.

TASK:
1. Scan the function_index.json for all known functions
2. For each decompiled function, extract its signature:
   - Return type (from Ghidra's decompilation)
   - Parameter types and names
   - Address
3. Group functions by system/module (based on naming, address proximity,
   or call relationships)
4. Generate header files in src/include/:
   - functions.h — all function prototypes
   - system_*.h — per-system headers (movement.h, battle.h, etc.)
5. Each prototype should have a comment with the function's address

EXAMPLE OUTPUT (src/include/functions.h):
// Auto-generated function prototypes
// Movement system
void scroll_update_a(int param1, int param2);  // 0x08043CD4
void scroll_update_b(int param1, int param2);  // 0x08043E78
void camera_follow_player(void);               // 0x0803BF88

OUTPUT:
{
  "headers_created": ["functions.h", "movement.h", "battle.h"],
  "prototypes_generated": 234,
  "modules_identified": ["movement", "battle", "dialogue", "save", "render"]
}
"""


class ForwardDeclGenerator(BaseAgent):

    @property
    def agent_type(self) -> str:
        return "refactor:forward_decl"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def build_context(self) -> str:
        parts = [
            "FORWARD DECLARATION GENERATOR: Create header files with function prototypes.\n",
            f"Project root: {self.project.root}",
            f"Source directory: {self.project.src_dir}",
        ]

        index_path = self.project.src_dir / "function_index.json"
        if index_path.exists():
            import json
            idx = json.loads(index_path.read_text())
            parts.append(f"Function index: {len(idx)} functions")
            # Count already-renamed functions
            named = [f for f in idx if not f["name"].startswith("FUN_")]
            parts.append(f"Already named: {len(named)} functions")

        parts.append("\nScan functions, extract signatures, generate headers.")
        return "\n".join(parts)

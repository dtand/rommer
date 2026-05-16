"""Forward declaration generator - scan call graph and generate prototypes."""

from rommer.agents.base import BaseAgent


class ForwardDeclGenerator(BaseAgent):
    """Scans call graph, generates function prototypes/headers."""

    @property
    def agent_type(self) -> str:
        return "refactor:forward_decl"

    def get_system_prompt(self) -> str:
        return (
            "You are a GBA reverse engineer generating forward declarations. "
            "Scan the decompiled functions' call graph and produce header files "
            "with proper function prototypes."
        )

    def build_context(self) -> str:
        # TODO: Full implementation in follow-up
        return (
            "FORWARD DECLARATION stage.\n"
            f"Source: {self.project.src_dir}\n"
            "Generate function prototypes from call graph analysis."
        )

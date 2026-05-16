"""System tracer - document complete systems and propose new discoveries."""

from rommer.agents.base import BaseAgent


class SystemTracer(BaseAgent):
    """Documents complete game systems, proposes new discoveries."""

    @property
    def agent_type(self) -> str:
        return "refactor:system_tracer"

    def get_system_prompt(self) -> str:
        return (
            "You are a GBA reverse engineer tracing complete game systems. "
            "Follow call chains to document how systems work end-to-end "
            "(e.g., the full collision check pipeline, the battle damage formula). "
            "Propose new memory address discoveries based on your analysis."
        )

    def build_context(self) -> str:
        # TODO: Full implementation in follow-up
        return (
            "SYSTEM TRACER stage.\n"
            f"Source: {self.project.src_dir}\n"
            "Trace complete systems and propose new discoveries."
        )

"""Base agent class for all rommer analysis agents."""

import json
import sqlite3
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from rommer.config import Project


class BaseAgent(ABC):
    """Abstract base class for all rommer agents.

    Lifecycle:
        1. __init__(project, focus) - configure
        2. build_context() - assemble prompt context from DB + knowledge
        3. spawn() - launch claude CLI subprocess
        4. complete(result) - process output, push discoveries to DB
    """

    def __init__(self, project: Project, focus: str | None = None, node_id: str | None = None):
        self.project = project
        self.focus = focus
        self.node_id = node_id
        self._db: sqlite3.Connection | None = None

    @property
    def db(self) -> sqlite3.Connection:
        if self._db is None:
            self._db = self.project.get_db()
        return self._db

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Agent type identifier (e.g., 'dynamic', 'static', 'refactor')."""
        ...

    @abstractmethod
    def build_context(self) -> str:
        """Build the full prompt context string for this agent."""
        ...

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent type."""
        ...

    # Preamble injected into all agent system prompts
    AGENT_PREAMBLE = """\
WORKSPACE RULES:
- Your working directory is the project root.
- If you need to create temporary files (scripts, extracted data, intermediate results),
  use the `tmp/` directory inside the project root.
- IMPORTANT: Before you finish, DELETE all files you created in `tmp/`. Do not leave
  artifacts in the project workspace. Only your final JSON output matters.
- Do not modify any files outside of `tmp/` unless explicitly instructed to.

"""

    def spawn(
        self,
        model: str = "opus",
        timeout: int = 3600,
        dry_run: bool = False,
        on_event: Callable[[dict], None] | None = None,
    ) -> dict | None:
        """Launch the agent as a claude CLI subprocess.

        Args:
            model: Claude model to use
            timeout: Max runtime in seconds
            dry_run: If True, print what would run without executing
            on_event: Streaming callback for live output (agent text, tool calls, etc.)

        Returns parsed result dict, or None if dry_run.
        """
        context = self.build_context()
        system_prompt = self.AGENT_PREAMBLE + self.get_system_prompt()

        if dry_run:
            print(f"[{self.agent_type}] Would spawn with:")
            print(f"  Model: {model}")
            print(f"  Timeout: {timeout}s")
            print(f"  Context length: {len(context)} chars")
            print(f"  System prompt length: {len(system_prompt)} chars")
            return None

        # Use streaming if callback provided
        if on_event:
            from rommer.preprocessor.claude import invoke_streaming
            return invoke_streaming(
                prompt=context,
                system_prompt=system_prompt,
                model=model,
                allowed_tools=self.allowed_tools,
                add_dirs=self.add_dirs,
                timeout=timeout,
                on_event=on_event,
            )

        from rommer.preprocessor.claude import invoke
        return invoke(
            prompt=context,
            system_prompt=system_prompt,
            model=model,
            allowed_tools=self.allowed_tools,
            add_dirs=self.add_dirs,
            timeout=timeout,
        )

    @property
    def allowed_tools(self) -> list[str]:
        """Tools the agent can use. Override to restrict."""
        return ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]

    @property
    def add_dirs(self) -> list[Path]:
        """Directories the agent can access."""
        return [self.project.root]

    def complete(self, result: dict) -> list[dict]:
        """Process agent output, push candidate discoveries to DB.

        Returns list of staged candidates.
        """
        candidates = result.get("candidates", [])
        staged = []

        for c in candidates:
            try:
                self.db.execute(
                    """INSERT INTO node_candidate
                       (node_id, label, address, before_value, after_value,
                        confidence, method, reasoning)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self.node_id or "unknown",
                        c.get("label", ""),
                        c.get("address", ""),
                        c.get("before_value", ""),
                        c.get("after_value", ""),
                        c.get("confidence", "medium"),
                        c.get("method", self.agent_type),
                        c.get("reasoning", ""),
                    ),
                )
                staged.append(c)
            except sqlite3.Error:
                pass

        if staged:
            self.db.commit()

        return staged

    def _parse_output(self, output: str) -> dict:
        """Parse claude CLI JSON output into result dict."""
        try:
            data = json.loads(output)
            # Claude output format: look for result in the response
            if isinstance(data, dict):
                return data
            return {"result": {"status": "unknown", "raw": output[:1000]}, "candidates": []}
        except json.JSONDecodeError:
            return {"result": {"status": "partial", "raw": output[:1000]}, "candidates": []}

    # --- Context helpers (shared by subclasses) ---

    def get_golden_discoveries(self) -> list[dict]:
        """Fetch all golden-tier discoveries from DB."""
        try:
            rows = self.db.execute(
                """SELECT label, address, data_type, confidence, schema_target, discovered_by_node
                   FROM discovery WHERE tier = 'golden'"""
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    def get_controls_reference(self) -> str:
        """Build formatted control mappings from DB."""
        try:
            rows = self.db.execute(
                "SELECT context, button, action FROM control_mapping ORDER BY context, button"
            ).fetchall()
        except sqlite3.OperationalError:
            return ""

        by_context: dict[str, list[str]] = {}
        for r in rows:
            ctx = r["context"]
            by_context.setdefault(ctx, []).append(f"  {r['button']}: {r['action']}")

        lines = []
        for ctx in sorted(by_context):
            lines.append(f"**{ctx.title()}:**")
            lines.extend(by_context[ctx])
            lines.append("")
        return "\n".join(lines)

    def get_node_data(self) -> dict | None:
        """Fetch node details from DB."""
        if not self.node_id:
            return None
        row = self.db.execute(
            """SELECT node_id, name, title, description, section_ref,
                      goal, success_criteria, tags, discovery_hints
               FROM graph_node WHERE node_id = ?""",
            (self.node_id,),
        ).fetchone()
        if not row:
            return None
        return {
            **dict(row),
            "tags": json.loads(row["tags"]) if row["tags"] else [],
            "discovery_hints": json.loads(row["discovery_hints"]) if row["discovery_hints"] else [],
        }

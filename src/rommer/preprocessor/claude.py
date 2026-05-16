"""Wrapper for invoking Claude Code CLI as a subprocess."""

import json
import os
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path


INTERRUPTED = "__interrupted__"


def invoke(
    prompt: str,
    system_prompt: str | None = None,
    model: str = "sonnet",
    allowed_tools: list[str] | None = None,
    add_dirs: list[Path] | None = None,
    timeout: int = 1200,
) -> dict | str:
    """Call `claude -p` and return parsed output.

    Returns parsed dict if response contains JSON, otherwise raw text.
    """
    cmd = ["claude", "-p", "--output-format", "json", "--model", model]

    tmp_files = []

    if system_prompt:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
        tmp.write(system_prompt)
        tmp.close()
        tmp_files.append(tmp.name)
        cmd.extend(["--system-prompt-file", tmp.name])

    if allowed_tools:
        cmd.extend(["--allowedTools", ",".join(allowed_tools)])

    if add_dirs:
        for d in add_dirs:
            cmd.extend(["--add-dir", str(d)])

    cmd.extend(["--no-session-persistence"])

    try:
        result = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=timeout,
        )
    finally:
        for f in tmp_files:
            try:
                os.unlink(f)
            except OSError:
                pass

    if result.returncode != 0:
        raise RuntimeError(
            f"Claude CLI failed (exit {result.returncode}):\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout[:500]}"
        )

    envelope = json.loads(result.stdout)
    if envelope.get("is_error"):
        raise RuntimeError(f"Claude CLI returned error: {envelope.get('result', envelope)}")

    return _parse_json(envelope.get("result", ""))


def invoke_streaming(
    prompt: str,
    system_prompt: str | None = None,
    model: str = "sonnet",
    allowed_tools: list[str] | None = None,
    add_dirs: list[Path] | None = None,
    timeout: int = 1200,
    on_event: Callable[[dict], None] | None = None,
    session_id: str | None = None,
    resume: bool = False,
    interrupt_event: threading.Event | None = None,
) -> dict | str:
    """Call `claude -p` with streaming output, emitting events as they arrive.

    Returns parsed dict, raw text, or INTERRUPTED sentinel.
    """
    cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--model", model]

    tmp_files = []

    if system_prompt and not resume:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
        tmp.write(system_prompt)
        tmp.close()
        tmp_files.append(tmp.name)
        cmd.extend(["--system-prompt-file", tmp.name])

    if allowed_tools:
        cmd.extend(["--allowedTools", ",".join(allowed_tools)])

    if add_dirs:
        for d in add_dirs:
            cmd.extend(["--add-dir", str(d)])

    if session_id:
        cmd.extend(["--session-id", session_id])
        if resume:
            cmd.append("--resume")
    else:
        cmd.extend(["--no-session-persistence"])

    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )

    result_text = ""
    was_interrupted = False

    try:
        proc.stdin.write(prompt)
        proc.stdin.close()

        if interrupt_event:
            def _watcher():
                nonlocal was_interrupted
                interrupt_event.wait()
                was_interrupted = True
                if proc.poll() is None:
                    proc.terminate()
            threading.Thread(target=_watcher, daemon=True).start()

        deadline = time.time() + timeout
        raw = ""
        for line in proc.stdout:
            if time.time() > deadline:
                proc.terminate()
                raise subprocess.TimeoutExpired(cmd, timeout)

            raw += line
            while "\n" in raw:
                json_str, raw = raw.split("\n", 1)
                json_str = json_str.strip()
                if not json_str:
                    continue
                try:
                    event = json.loads(json_str)
                except json.JSONDecodeError:
                    continue

                if event.get("type") == "assistant" and on_event:
                    for block in event.get("message", {}).get("content", []):
                        if block.get("type") == "text":
                            on_event({"type": "agent_text", "text": block.get("text", "")})
                        elif block.get("type") == "tool_use":
                            on_event({"type": "agent_tool_call", "tool": block.get("name", ""), "input": block.get("input", {})})

                if event.get("type") == "result":
                    result_text = event.get("result", "")
                    if event.get("is_error"):
                        raise RuntimeError(f"Claude CLI error: {result_text}")

        proc.wait(timeout=10)
    finally:
        for f in tmp_files:
            try:
                os.unlink(f)
            except OSError:
                pass
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    if was_interrupted:
        return INTERRUPTED

    return _parse_json(result_text)


def _parse_json(text: str) -> dict | str:
    """Try to extract JSON from response text."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    if "```" in text:
        start = text.index("```") + 3
        newline = text.index("\n", start)
        end = text.index("```", newline)
        try:
            return json.loads(text[newline:end])
        except json.JSONDecodeError:
            pass

    return text

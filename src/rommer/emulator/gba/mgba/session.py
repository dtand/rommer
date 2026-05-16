"""Interactive emulator session - single ROM load, commands via stdin/stdout.

The agent sends commands line by line on stdin, gets JSON responses on stdout.
The emulator stays alive the entire session. Snapshots are held in memory.
"""

import json
import shlex
import sys
import time
from pathlib import Path

from rommer.emulator.gba.base import GBAEmulator
from rommer.emulator.gba.mgba.core import MgbaEmulator


class EmulatorSession:
    """Interactive emulator session with in-memory snapshots."""

    def __init__(self, rom_path: str, state_path: str, workdir: str):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        (self.workdir / "evidence").mkdir(exist_ok=True)
        self.rom_path = rom_path

        self.emu: GBAEmulator = MgbaEmulator(rom_path)
        self.emu.load_state(state_path)
        self._memory_snapshots: dict[str, bytes] = {}
        self._state_snapshots: dict[str, bytes] = {}
        self._log: list[dict] = []
        self._step = 0
        self._last_screenshot: str | None = None
        self._current_command: str | None = None
        self._auto_screenshot: bool = False
        self._auto_screenshot_seq: int = 0

        print(json.dumps({"status": "ready", "rom": rom_path, "state": state_path,
                           "workdir": str(self.workdir)}), flush=True)

    def run(self):
        """Read commands from stdin, execute, respond on stdout."""
        for line in sys.stdin:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                parts = shlex.split(line)
                cmd = parts[0].lower().replace("-", "_")
                handler = getattr(self, f"_cmd_{cmd}", None)
                if handler is None:
                    self._respond({"error": f"Unknown command: {parts[0]}"})
                    continue
                self._current_command = line
                handler(parts[1:])
            except SystemExit:
                return
            except Exception as e:
                self._respond({"error": str(e)})

    def _respond(self, data: dict):
        print(json.dumps(data), flush=True)
        if self._current_command is not None:
            self._step += 1
            entry = {
                "step": self._step,
                "timestamp": time.time(),
                "command": self._current_command,
                "response": data,
            }
            self._log.append(entry)

    def _write_log(self):
        log_path = self.workdir / "execution_log.json"
        log_path.write_text(json.dumps(self._log, indent=2))

    def _parse_flags(self, args: list[str], flags: dict[str, type]) -> tuple[list[str], dict]:
        positional = []
        parsed = {}
        i = 0
        while i < len(args):
            if args[i].startswith("--") and args[i][2:] in flags:
                key = args[i][2:]
                parsed[key] = flags[key](args[i + 1])
                i += 2
            else:
                positional.append(args[i])
                i += 1
        return positional, parsed

    # -- Commands --

    def _cmd_press(self, args: list[str]):
        keys, flags = self._parse_flags(args, {"frames": int, "wait": int})
        frames = flags.get("frames", 5)
        wait = flags.get("wait", 0)
        self.emu.press(keys, frames=frames)
        if wait > 0:
            self.emu.run_frames(wait)
        self._respond({"ok": True, "keys": keys, "frames": frames,
                        "total_frames": self.emu.frame_count})

    def _cmd_run(self, args: list[str]):
        count = int(args[0]) if args else 1
        self.emu.run_frames(count)
        self._respond({"ok": True, "frames": count, "total_frames": self.emu.frame_count})

    def _cmd_screenshot(self, args: list[str]):
        path = self.workdir / args[0] if args else self.workdir / "screenshot.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.emu.screenshot(path)
        self._respond({"ok": True, "path": str(path)})

    def _cmd_snapshot(self, args: list[str]):
        positional, flags = self._parse_flags(args, {"region": str})
        name = positional[0] if positional else "default"
        region = flags.get("region", "ewram")
        data = self.emu.memory_snapshot(region)
        self._memory_snapshots[f"{name}:{region}"] = data
        self._respond({"ok": True, "snapshot": name, "region": region, "size": len(data)})

    def _cmd_diff(self, args: list[str]):
        positional, flags = self._parse_flags(args, {"region": str, "limit": int})
        if len(positional) < 2:
            self._respond({"error": "Usage: diff <snap_a> <snap_b> [--region ewram] [--limit N]"})
            return
        name_a, name_b = positional[0], positional[1]
        region = flags.get("region", "ewram")
        limit = flags.get("limit", 100)
        base = GBAEmulator.REGIONS.get(region, (0x02000000, 0))[0]

        key_a, key_b = f"{name_a}:{region}", f"{name_b}:{region}"
        if key_a not in self._memory_snapshots or key_b not in self._memory_snapshots:
            available = sorted(set(k.split(":")[0] for k in self._memory_snapshots))
            self._respond({"error": f"Snapshot not found. Available: {available}"})
            return

        a, b = self._memory_snapshots[key_a], self._memory_snapshots[key_b]
        changes = []
        total = 0
        for i in range(len(a)):
            if a[i] != b[i]:
                total += 1
                if len(changes) < limit:
                    changes.append({"address": f"0x{base + i:08x}", "before": a[i], "after": b[i]})

        self._respond({"ok": True, "total_changes": total, "changes": changes})

    def _cmd_read(self, args: list[str]):
        positional, flags = self._parse_flags(args, {"size": int, "format": str})
        addr = int(positional[0], 0)
        size = flags.get("size", 16)
        data = self.emu.read_memory(addr, size)
        formatted = [f"0x{b:02x}" for b in data]
        self._respond({"ok": True, "address": f"0x{addr:08x}", "data": formatted})

    def _cmd_write(self, args: list[str]):
        positional, flags = self._parse_flags(args, {"width": int})
        addr = int(positional[0], 0)
        val = int(positional[1], 0)
        width = flags.get("width", 8)
        if width == 8:
            self.emu.write_memory(addr, val.to_bytes(1, "little"))
        elif width == 16:
            self.emu.write_memory(addr, val.to_bytes(2, "little"))
        elif width == 32:
            self.emu.write_memory(addr, val.to_bytes(4, "little"))
        self._respond({"ok": True, "address": f"0x{addr:08x}", "value": f"0x{val:x}"})

    def _cmd_scan_value(self, args: list[str]):
        positional, flags = self._parse_flags(args, {"width": int, "region": str})
        val = int(positional[0], 0)
        width = flags.get("width", 8)
        region = flags.get("region", "ewram")
        data = self.emu.memory_snapshot(region)
        base = GBAEmulator.REGIONS.get(region, (0x02000000, 0))[0]
        matches = []

        if width == 8:
            for i in range(len(data)):
                if data[i] == (val & 0xFF):
                    matches.append(f"0x{base + i:08x}")
        elif width == 16:
            for i in range(0, len(data) - 1, 2):
                v = data[i] | (data[i + 1] << 8)
                if v == (val & 0xFFFF):
                    matches.append(f"0x{base + i:08x}")
        elif width == 32:
            for i in range(0, len(data) - 3, 4):
                v = data[i] | (data[i + 1] << 8) | (data[i + 2] << 16) | (data[i + 3] << 24)
                if v == (val & 0xFFFFFFFF):
                    matches.append(f"0x{base + i:08x}")

        self._respond({"ok": True, "value": f"0x{val:x}", "matches": matches, "count": len(matches)})

    def _cmd_info(self, args: list[str]):
        self._respond({
            "ok": True, "total_frames": self.emu.frame_count,
            "snapshots": sorted(set(k.split(":")[0] for k in self._memory_snapshots)),
            "savepoints": list(self._state_snapshots.keys()),
        })

    def _cmd_help(self, args: list[str]):
        cmds = [
            "press <keys...> [--frames N] [--wait N]",
            "run <count>", "screenshot <path>",
            "snapshot <name> [--region ewram|iwram]",
            "diff <a> <b> [--region ewram] [--limit N]",
            "read <0xADDR> [--size N]", "write <0xADDR> <value> [--width 8|16|32]",
            "scan-value <value> [--width 8|16|32] [--region ewram]",
            "info", "quit",
        ]
        self._respond({"commands": cmds})

    def _cmd_quit(self, args: list[str]):
        self._write_log()
        self._respond({"status": "closed", "total_frames": self.emu.frame_count})
        self.emu.close()
        sys.exit(0)

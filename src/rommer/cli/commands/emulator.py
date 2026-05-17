"""rommer emulator - launch mGBA with a project's ROM and save state."""

import os
import subprocess
import sys

from rommer.config import Project


def handler(args):
    project = Project(args.project)
    if not project.exists():
        print(f"Error: project '{args.project}' not found")
        raise SystemExit(1)

    rom_path = project.rom_path
    if not rom_path.exists():
        print(f"Error: ROM not found at {rom_path}")
        raise SystemExit(1)

    # Find save state
    state_path = None
    if args.save_state:
        state_path = project.save_states_dir / args.save_state
        if not state_path.exists():
            print(f"Error: save state not found: {state_path}")
            print(f"Available: {[f.name for f in project.save_states_dir.iterdir() if f.is_file()]}")
            raise SystemExit(1)
    else:
        # Pick first available
        if project.save_states_dir.exists():
            saves = [f for f in sorted(project.save_states_dir.iterdir()) if f.is_file() and not f.name.startswith(".")]
            if saves:
                state_path = saves[0]

    if args.headless:
        _run_headless(rom_path, state_path, args.port)
    else:
        _run_gui(rom_path, state_path)


def _find_mgba():
    """Find the mGBA binary."""
    paths = [
        os.environ.get("MGBA_PATH", ""),
        os.path.expanduser("~/Desktop/ROMS/mGBA.app"),
        "/Applications/mGBA.app",
    ]
    for p in paths:
        binary = os.path.join(p, "Contents/MacOS/mGBA") if p.endswith(".app") else p
        if os.path.exists(binary):
            return binary
    return None


def _run_gui(rom_path, state_path):
    """Launch mGBA GUI with optional save state."""
    mgba = _find_mgba()
    if not mgba:
        print("Error: mGBA not found. Set MGBA_PATH env var.")
        raise SystemExit(1)

    cmd = [mgba]
    if state_path:
        cmd.extend(["-t", str(state_path)])
        print(f"Loading save state: {state_path.name}")
    cmd.append(str(rom_path))

    print(f"Launching mGBA: {rom_path.name}")
    subprocess.Popen(cmd)


def _run_headless(rom_path, state_path, port):
    """Launch mGBA as a headless TCP server."""
    if not state_path:
        print("Error: headless mode requires a save state (--save-state)")
        raise SystemExit(1)

    env = os.environ.copy()
    mgba_lib = env.get("MGBA_LIB_PATH", "/tmp/mgba-src/build")
    env["DYLD_LIBRARY_PATH"] = mgba_lib

    cmd = [
        sys.executable, "-m", "rommer.emulator.gba.mgba.server",
        "--rom", str(rom_path),
        "--state", str(state_path),
        "--workdir", "/tmp/rommer-emulator",
        "--port", str(port),
    ]

    print(f"Starting emulator server on port {port}")
    print(f"ROM: {rom_path.name}")
    print(f"State: {state_path.name}")
    print(f"Send commands: echo \"help\" | nc localhost {port}")

    try:
        subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        print("\nServer stopped.")

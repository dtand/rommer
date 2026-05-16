"""TCP server wrapper for emulator session.

Allows agents to send commands over TCP instead of stdin/stdout.
"""

import argparse
import json
import socketserver
import sys
from pathlib import Path

from rommer.emulator.gba.mgba.session import EmulatorSession


class EmulatorRequestHandler(socketserver.StreamRequestHandler):
    """Handle a single TCP connection with emulator commands."""

    def handle(self):
        session: EmulatorSession = self.server.session
        for line in self.rfile:
            line = line.decode().strip()
            if not line:
                continue
            # Redirect session output to this connection
            old_stdout = sys.stdout

            class SocketWriter:
                def __init__(self, wfile):
                    self._wfile = wfile
                def write(self, s):
                    self._wfile.write(s.encode())
                def flush(self):
                    self._wfile.flush()

            sys.stdout = SocketWriter(self.wfile)
            try:
                import shlex
                parts = shlex.split(line)
                cmd = parts[0].lower().replace("-", "_")

                if cmd == "quit":
                    session._write_log()
                    response = json.dumps({"status": "closed", "total_frames": session.emu.frame_count})
                    self.wfile.write(f"{response}\n".encode())
                    self.wfile.flush()
                    return

                handler = getattr(session, f"_cmd_{cmd}", None)
                if handler is None:
                    response = json.dumps({"error": f"Unknown command: {parts[0]}"})
                    self.wfile.write(f"{response}\n".encode())
                    self.wfile.flush()
                    continue
                session._current_command = line
                handler(parts[1:])
            except Exception as e:
                response = json.dumps({"error": str(e)})
                self.wfile.write(f"{response}\n".encode())
                self.wfile.flush()
            finally:
                sys.stdout = old_stdout


class EmulatorServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, host, port, session):
        self.session = session
        super().__init__((host, port), EmulatorRequestHandler)


def main():
    parser = argparse.ArgumentParser(description="mGBA emulator TCP server")
    parser.add_argument("--rom", required=True, help="ROM file path")
    parser.add_argument("--state", required=True, help="Save state to load")
    parser.add_argument("--workdir", required=True, help="Working directory for output")
    parser.add_argument("--port", type=int, default=9123, help="TCP port (default: 9123)")
    args = parser.parse_args()

    session = EmulatorSession(args.rom, args.state, args.workdir)
    server = EmulatorServer("localhost", args.port, session)
    print(f"Emulator server listening on port {args.port}", file=sys.stderr)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        session.emu.close()
        server.server_close()


if __name__ == "__main__":
    main()

"""mGBA emulator wrapper - implements GBAEmulator interface.

Requires mGBA Python bindings (mgba-py) and the mGBA shared library.
Set MGBA_LIB_PATH env var to the directory containing libmgba.dylib.
"""

import os
from pathlib import Path

from rommer.emulator.gba.base import GBAEmulator


def _setup_lib_path():
    """Ensure the mGBA shared library is findable."""
    mgba_lib = os.environ.get("MGBA_LIB_PATH", "/tmp/mgba-src/build")
    current = os.environ.get("DYLD_LIBRARY_PATH", "")
    if mgba_lib not in current:
        os.environ["DYLD_LIBRARY_PATH"] = f"{mgba_lib}:{current}" if current else mgba_lib


class MgbaEmulator(GBAEmulator):
    """mGBA-based GBA emulator implementation.

    Uses mGBA Python bindings (mgba-py) with FFI for fast memory access.
    """

    KEYS = {
        "A": "KEY_A",
        "B": "KEY_B",
        "UP": "KEY_UP",
        "DOWN": "KEY_DOWN",
        "LEFT": "KEY_LEFT",
        "RIGHT": "KEY_RIGHT",
        "START": "KEY_START",
        "SELECT": "KEY_SELECT",
        "L": "KEY_L",
        "R": "KEY_R",
    }

    def __init__(self, rom_path: str | Path | None = None):
        self.core = None
        self._buf = None
        self.width = 0
        self.height = 0
        self._frame_count = 0

        if rom_path:
            self.load_rom(rom_path)

    def load_rom(self, path: str | Path) -> None:
        """Load a GBA ROM file."""
        _setup_lib_path()
        import mgba.core
        import mgba.log
        from mgba._pylib import ffi

        mgba.log.silence()

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"ROM not found: {path}")

        self.core = mgba.core.load_path(str(path))
        self.width, self.height = self.core.desired_video_dimensions()
        self._buf = ffi.new(f"color_t[{self.width * self.height}]")
        self.core._core.setVideoBuffer(self.core._core, self._buf, self.width)
        self.core.reset()
        self._frame_count = 0

    def load_state(self, path: str | Path) -> None:
        """Load emulator state from file (supports .state and .ss0 PNG containers)."""
        from mgba._pylib import ffi

        path = Path(path)
        raw = path.read_bytes()

        # Detect mGBA GUI PNG container (starts with PNG magic)
        if raw[:8] == b'\x89PNG\r\n\x1a\n':
            raw = self._extract_state_from_png(raw)

        buf = ffi.new("unsigned char[]", len(raw))
        ffi.memmove(buf, raw, len(raw))
        self.core.load_raw_state(buf)

    def save_state(self, path: str | Path) -> None:
        """Save emulator state to file."""
        from mgba._pylib import ffi

        state = self.core.save_raw_state()
        state_bytes = ffi.buffer(state)[:]
        Path(path).write_bytes(state_bytes)

    def run_frames(self, count: int = 1) -> None:
        """Advance the emulator by N frames."""
        for _ in range(count):
            self.core.run_frame()
            self._frame_count += 1

    def press(self, keys: list[str], frames: int = 5) -> None:
        """Press keys for N frames, then release."""
        mask = 0
        for key in keys:
            attr = self.KEYS.get(key.upper())
            if attr is None:
                raise ValueError(f"Unknown key: {key}. Valid: {list(self.KEYS.keys())}")
            mask |= getattr(self.core, attr)

        self.core.set_keys(mask)
        self.run_frames(frames)
        self.core.clear_keys(mask)

    def read_memory(self, address: int, size: int = 1) -> bytes:
        """Read `size` bytes starting at `address`."""
        mem = self.core.memory.u8
        return bytes(mem[address + i] for i in range(size))

    def write_memory(self, address: int, data: bytes) -> None:
        """Write bytes to memory at `address`."""
        mem = self.core.memory.u8
        for i, b in enumerate(data):
            mem[address + i] = b

    def read_u8(self, address: int) -> int:
        return self.core.memory.u8[address]

    def read_u16(self, address: int) -> int:
        return self.core.memory.u16[address]

    def read_u32(self, address: int) -> int:
        return self.core.memory.u32[address]

    def write_u8(self, address: int, value: int):
        self.core.memory.u8[address] = value

    def write_u16(self, address: int, value: int):
        self.core.memory.u16[address] = value

    def write_u32(self, address: int, value: int):
        self.core.memory.u32[address] = value

    def screenshot(self, path: str | Path) -> None:
        """Save the current frame as a PNG with fixed alpha."""
        from mgba._pylib import ffi
        from PIL import Image

        pixels = bytearray(ffi.buffer(self._buf, self.width * self.height * 4))
        for i in range(3, len(pixels), 4):
            pixels[i] = 255
        img = Image.frombytes("RGBA", (self.width, self.height), bytes(pixels))
        img.save(str(path))

    def close(self) -> None:
        """Release resources."""
        if self.core:
            self.core = None
        self._buf = None

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @staticmethod
    def _extract_state_from_png(data: bytes) -> bytes:
        """Extract raw state data from an mGBA GUI .ss* PNG container."""
        import struct
        import zlib

        pos = 8  # skip PNG header
        while pos < len(data):
            length = struct.unpack(">I", data[pos:pos + 4])[0]
            chunk_type = data[pos + 4:pos + 8]
            chunk_data = data[pos + 8:pos + 8 + length]
            pos += 12 + length

            if chunk_type == b"gbAs":
                return zlib.decompress(chunk_data)
            if chunk_type == b"IEND":
                break

        raise ValueError("No gbAs chunk found in PNG state file")

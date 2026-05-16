"""GBA-specific emulator base - memory map constants and convenience methods."""

from rommer.emulator.base import BaseEmulator


class GBAEmulator(BaseEmulator):
    """GBA platform emulator with memory map constants and region helpers.

    Subclasses (MgbaEmulator, etc.) implement the actual emulation.
    """

    # GBA Memory Map
    ROM_BASE = 0x08000000
    ROM_SIZE = 0x02000000  # 32MB max

    EWRAM_BASE = 0x02000000
    EWRAM_SIZE = 0x00040000  # 256KB

    IWRAM_BASE = 0x03000000
    IWRAM_SIZE = 0x00008000  # 32KB

    IO_BASE = 0x04000000
    IO_SIZE = 0x00000400

    PALETTE_BASE = 0x05000000
    PALETTE_SIZE = 0x00000400

    VRAM_BASE = 0x06000000
    VRAM_SIZE = 0x00018000  # 96KB

    OAM_BASE = 0x07000000
    OAM_SIZE = 0x00000400

    REGIONS = {
        "rom": (ROM_BASE, ROM_SIZE),
        "ewram": (EWRAM_BASE, EWRAM_SIZE),
        "iwram": (IWRAM_BASE, IWRAM_SIZE),
        "io": (IO_BASE, IO_SIZE),
        "palette": (PALETTE_BASE, PALETTE_SIZE),
        "vram": (VRAM_BASE, VRAM_SIZE),
        "oam": (OAM_BASE, OAM_SIZE),
    }

    # GBA Buttons
    BUTTONS = ["A", "B", "UP", "DOWN", "LEFT", "RIGHT", "START", "SELECT", "L", "R"]

    def read_ewram(self, offset: int, size: int = 1) -> bytes:
        """Read from EWRAM at offset (relative to EWRAM base)."""
        return self.read_memory(self.EWRAM_BASE + offset, size)

    def read_iwram(self, offset: int, size: int = 1) -> bytes:
        """Read from IWRAM at offset (relative to IWRAM base)."""
        return self.read_memory(self.IWRAM_BASE + offset, size)

    def memory_snapshot(self, region: str = "ewram") -> bytes:
        """Capture a full memory region as bytes."""
        if region not in self.REGIONS:
            raise ValueError(f"Unknown region: {region}. Valid: {list(self.REGIONS.keys())}")
        base, size = self.REGIONS[region]
        return self.read_memory(base, size)

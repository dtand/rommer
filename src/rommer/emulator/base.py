"""Base emulator interface - platform-agnostic abstraction."""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseEmulator(ABC):
    """Abstract base class for all emulator implementations.

    Provides a platform-agnostic interface for ROM execution,
    memory access, input, and state management.
    """

    @abstractmethod
    def load_rom(self, path: str | Path) -> None:
        """Load a ROM file."""
        ...

    @abstractmethod
    def load_state(self, path: str | Path) -> None:
        """Load emulator state from file."""
        ...

    @abstractmethod
    def save_state(self, path: str | Path) -> None:
        """Save emulator state to file."""
        ...

    @abstractmethod
    def run_frames(self, count: int = 1) -> None:
        """Advance emulation by N frames."""
        ...

    @abstractmethod
    def press(self, keys: list[str], frames: int = 5) -> None:
        """Press keys for N frames, then release."""
        ...

    @abstractmethod
    def read_memory(self, address: int, size: int = 1) -> bytes:
        """Read `size` bytes starting at `address`."""
        ...

    @abstractmethod
    def write_memory(self, address: int, data: bytes) -> None:
        """Write bytes to memory at `address`."""
        ...

    @abstractmethod
    def screenshot(self, path: str | Path) -> None:
        """Save current frame as PNG."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release resources."""
        ...

    @property
    @abstractmethod
    def frame_count(self) -> int:
        """Total frames executed since ROM load."""
        ...

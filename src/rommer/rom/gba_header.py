"""GBA ROM header parser.

GBA ROM Header Layout (0x000-0x0BF):
  0x000-0x003: Entry point (ARM branch instruction)
  0x004-0x09F: Nintendo logo (compressed bitmap)
  0x0A0-0x0AB: Game title (12 bytes, uppercase ASCII, padded with 0x00)
  0x0AC-0x0AF: Game code (4 bytes)
  0x0B0-0x0B1: Maker code (2 bytes)
  0x0B2:       Fixed value (must be 0x96)
  0x0B3:       Main unit code (0x00 for GBA)
  0x0B4:       Device type
  0x0B5-0x0BB: Reserved (7 bytes, should be zero)
  0x0BC:       Software version
  0x0BD:       Complement check (header checksum)
  0x0BE-0x0BF: Reserved (2 bytes)
"""

from pathlib import Path


# Known maker codes
MAKER_CODES = {
    "01": "Nintendo",
    "08": "Capcom",
    "13": "Electronic Arts",
    "20": "Destination Software",
    "34": "Konami",
    "41": "Ubisoft",
    "4F": "Eidos",
    "52": "Activision",
    "54": "Rockstar Games",
    "5G": "Majesco",
    "64": "LucasArts",
    "69": "Electronic Arts",
    "6S": "TDK Mediactive",
    "78": "THQ",
    "7D": "Sierra",
    "8P": "Sega",
    "A4": "Mirage",
    "AF": "Namco",
    "B2": "Bandai",
    "E9": "Natsume",
    "G9": "D3 Publisher",
}


def parse_gba_header(rom_path: str | Path) -> dict | None:
    """Parse GBA ROM header and return metadata dict.

    Returns None if the file is not a valid GBA ROM.
    """
    path = Path(rom_path)
    if not path.exists():
        return None

    data = path.read_bytes()[:0xC0]
    if len(data) < 0xC0:
        return None

    # Validate fixed byte at 0xB2
    if data[0xB2] != 0x96:
        return None

    # Parse fields
    game_title = data[0xA0:0xAC].decode("ascii", errors="replace").rstrip("\x00").strip()
    game_code = data[0xAC:0xB0].decode("ascii", errors="replace").rstrip("\x00")
    maker_code = data[0xB0:0xB2].decode("ascii", errors="replace").rstrip("\x00")
    software_version = data[0xBC]

    # Derive platform region from game code
    # Game code format: XYYY where X=type, YYY=game ID
    # Last char often indicates region: E=USA, J=Japan, P=Europe
    region = "Unknown"
    if len(game_code) == 4:
        region_char = game_code[3]
        region_map = {"E": "USA", "J": "Japan", "P": "Europe", "F": "France", "D": "Germany", "S": "Spain", "I": "Italy"}
        region = region_map.get(region_char, f"Unknown ({region_char})")

    # ROM size
    rom_size = path.stat().st_size
    rom_size_mb = rom_size / (1024 * 1024)

    # Header checksum validation
    checksum = 0
    for i in range(0xA0, 0xBD):
        checksum = (checksum - data[i]) & 0xFF
    checksum = (checksum - 0x19) & 0xFF
    checksum_valid = checksum == data[0xBD]

    return {
        "game_title": game_title,
        "game_code": game_code,
        "maker_code": maker_code,
        "maker_name": MAKER_CODES.get(maker_code, f"Unknown ({maker_code})"),
        "software_version": software_version,
        "region": region,
        "rom_size_bytes": rom_size,
        "rom_size_mb": round(rom_size_mb, 2),
        "checksum_valid": checksum_valid,
    }

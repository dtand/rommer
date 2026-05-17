"""Literal pool resolver — resolve DAT_08XXXXXX references from ROM binary.

Reads the ROM at each DAT_ offset and adds a comment showing the actual value.
Cross-references with discoveries for named labels.
"""

import json
import re
import struct
from pathlib import Path


def resolve_literals(src_dir: Path, rom_path: Path, discoveries: list[dict] | None = None) -> dict:
    """Resolve DAT_ literal pool references in all function files.

    Args:
        src_dir: Source directory with functions/
        rom_path: Path to the ROM binary
        discoveries: Optional list of discovery dicts for label cross-referencing

    Returns stats dict.
    """
    funcs_dir = src_dir / "functions"
    if not funcs_dir.exists():
        return {"error": "No functions directory"}
    if not rom_path.exists():
        return {"error": f"ROM not found: {rom_path}"}

    rom = rom_path.read_bytes()
    rom_base = 0x08000000

    # Build discovery lookup by address
    disc_by_addr: dict[int, str] = {}
    if discoveries:
        for d in discoveries:
            try:
                addr = int(d["address"], 16)
                disc_by_addr[addr] = d["label"]
            except (ValueError, KeyError):
                pass

    # Find all unique DAT_ references
    dat_pattern = re.compile(r'\bDAT_([0-9a-fA-F]{8})\b')

    resolved = 0
    files_modified = 0
    pointers_to_rom = 0
    pointers_to_iwram = 0
    pointers_to_ewram = 0
    constants = 0

    # Build global DAT_ resolution map
    dat_values: dict[str, dict] = {}

    for f in funcs_dir.glob("*.c"):
        content = f.read_text()
        dats = set(dat_pattern.findall(content))

        for dat_hex in dats:
            dat_key = f"DAT_{dat_hex}"
            if dat_key in dat_values:
                continue

            dat_addr = int(dat_hex, 16)

            # Only resolve ROM-space DAT_ (0x08XXXXXX)
            if dat_addr < rom_base or dat_addr >= rom_base + len(rom):
                continue

            offset = dat_addr - rom_base
            if offset + 4 > len(rom):
                continue

            value = struct.unpack_from("<I", rom, offset)[0]
            resolved += 1

            # Classify the value
            label = disc_by_addr.get(value, "")
            if 0x08000000 <= value < 0x0A000000:
                category = "ROM pointer"
                pointers_to_rom += 1
            elif 0x03000000 <= value < 0x03008000:
                category = "IWRAM"
                pointers_to_iwram += 1
            elif 0x02000000 <= value < 0x02040000:
                category = "EWRAM"
                pointers_to_ewram += 1
            elif 0x04000000 <= value < 0x04000400:
                category = "IO register"
            elif 0x05000000 <= value < 0x08000000:
                category = "VRAM/OAM/Palette"
            else:
                category = "constant"
                constants += 1

            dat_values[dat_key] = {
                "value": value,
                "hex": f"0x{value:08X}",
                "category": category,
                "label": label,
            }

    # Apply comments to files
    for f in funcs_dir.glob("*.c"):
        content = f.read_text()
        dats = set(dat_pattern.findall(content))

        modified = False
        for dat_hex in dats:
            dat_key = f"DAT_{dat_hex}"
            if dat_key not in dat_values:
                continue

            info = dat_values[dat_key]
            comment = f"/* {dat_key} = {info['hex']} ({info['category']}"
            if info["label"]:
                comment += f" = {info['label']}"
            comment += ") */"

            # Add comment after first occurrence of this DAT_ if not already commented
            marker = f"{dat_key} {comment}"
            if comment not in content:
                # Replace first bare DAT_ reference with commented version
                content = content.replace(dat_key, f"{dat_key} {comment}", 1)
                modified = True

        if modified:
            f.write_text(content)
            files_modified += 1

    # Save resolution map
    map_path = src_dir / "literal_pool_map.json"
    map_path.write_text(json.dumps(dat_values, indent=2))

    return {
        "resolved": resolved,
        "files_modified": files_modified,
        "pointers_to_rom": pointers_to_rom,
        "pointers_to_iwram": pointers_to_iwram,
        "pointers_to_ewram": pointers_to_ewram,
        "constants": constants,
        "with_discovery_labels": sum(1 for v in dat_values.values() if v["label"]),
    }

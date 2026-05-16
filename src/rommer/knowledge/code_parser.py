"""Parse cheat code files (CodeBreaker, Action Replay, GameShark) into discoveries."""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from rommer.config import Project


def parse_project_codes(project: Project) -> int:
    """Parse all code files in a project's knowledge/codes/ directory.

    Returns number of discoveries inserted.
    """
    codes_dir = project.knowledge_dir / "codes"
    if not codes_dir.exists():
        return 0

    discoveries = []
    for f in codes_dir.iterdir():
        if f.suffix.lower() == ".xml":
            discoveries.extend(parse_codebreaker_xml(f))
        elif f.suffix.lower() in (".txt", ".cht"):
            discoveries.extend(parse_text_codes(f))

    if not discoveries:
        return 0

    # Insert as golden discoveries
    conn = project.get_db()
    project_id = conn.execute("SELECT id FROM project LIMIT 1").fetchone()
    project_id = project_id[0] if project_id else 0

    inserted = 0
    for d in discoveries:
        # Skip if already exists
        existing = conn.execute(
            "SELECT id FROM discovery WHERE address = ? AND label = ?",
            (d["address"], d["label"]),
        ).fetchone()
        if existing:
            continue

        conn.execute(
            """INSERT INTO discovery
               (project_id, label, address, data_type, tier, confidence, source, discovery_method, notes)
               VALUES (?, ?, ?, ?, 'golden', 'confirmed', 'codebreaker', 'code_parse', ?)""",
            (project_id, d["label"], d["address"], d.get("data_type", "u16"),
             d.get("notes", "")),
        )
        inserted += 1

    conn.commit()
    conn.close()
    return inserted


def parse_codebreaker_xml(path: Path) -> list[dict]:
    """Parse CodeBreaker XML format.

    Expected structure:
    <codelist>
      <game name="...">
        <code name="description">
          XXXXXXXX YYYY
        </code>
      </game>
    </codelist>
    """
    discoveries = []
    try:
        tree = ET.parse(path)
        root = tree.getroot()

        for game in root.iter("game"):
            for code in game.iter("code"):
                name = code.get("name", "")
                text = (code.text or "").strip()
                parsed = _parse_code_lines(text, name)
                discoveries.extend(parsed)

        # Also try flat format: <cheat><name>...</name><code>...</code></cheat>
        for cheat in root.iter("cheat"):
            name_el = cheat.find("name")
            code_el = cheat.find("code")
            if name_el is not None and code_el is not None:
                name = name_el.text or ""
                text = (code_el.text or "").strip()
                parsed = _parse_code_lines(text, name)
                discoveries.extend(parsed)

    except (ET.ParseError, Exception):
        pass

    return discoveries


def parse_text_codes(path: Path) -> list[dict]:
    """Parse plain text code files (one code per line or block)."""
    discoveries = []
    try:
        text = path.read_text(errors="replace")
        current_label = ""

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            # Line with hex code pattern: XXXXXXXX YYYY or XXXXXXXX:YYYY
            if re.match(r'^[0-9A-Fa-f]{8}[\s:][0-9A-Fa-f]{4}', line):
                parsed = _parse_code_lines(line, current_label)
                discoveries.extend(parsed)
            elif not line.startswith(("#", "//", ";")):
                # Treat as label for next code
                current_label = line
    except Exception:
        pass

    return discoveries


def _parse_code_lines(text: str, label: str) -> list[dict]:
    """Parse individual code lines into discoveries.

    CodeBreaker format: TTAAAAAA YYYY
    - TT = code type (3 = 16-bit write, 8 = 8-bit write, etc.)
    - AAAAAA = address (offset into GBA memory)
    - YYYY = value
    """
    discoveries = []

    for line in text.splitlines():
        line = line.strip()
        match = re.match(r'^([0-9A-Fa-f]{8})[\s:]([0-9A-Fa-f]{4,8})', line)
        if not match:
            continue

        raw_addr = match.group(1)
        value = match.group(2)

        # Decode CodeBreaker type and address
        code_type = int(raw_addr[0], 16)
        address_offset = int(raw_addr[1:], 16)

        # Map to GBA memory (CodeBreaker uses IWRAM-relative for most codes)
        # Type 3: 16-bit constant write to 0x03000000 + offset
        # Type 8: 8-bit constant write
        # Type 0: 32-bit constant write
        if code_type == 3:
            address = f"0x{0x03000000 + address_offset:08x}"
            data_type = "u16"
        elif code_type == 8:
            address = f"0x{0x03000000 + address_offset:08x}"
            data_type = "u8"
        elif code_type == 0:
            address = f"0x{0x03000000 + address_offset:08x}"
            data_type = "u32"
        else:
            # Other types (conditional, etc.) - still record the address
            address = f"0x{0x03000000 + address_offset:08x}"
            data_type = "u16"

        discoveries.append({
            "label": label or f"code_{address}",
            "address": address,
            "data_type": data_type,
            "notes": f"Value: 0x{value} (type {code_type})",
        })

    return discoveries

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
    """Parse CodeBreaker/Action Replay codes from XML files.

    Handles multiple formats:
    1. Standard codelist XML: <codelist><game><code>...</code></game></codelist>
    2. Word XML documents containing embedded codes (Word 2003 XML)
    3. Flat cheat format: <cheat><name>...</name><code>...</code></cheat>
    """
    discoveries = []
    try:
        raw = path.read_text(errors="replace")

        # Detect Word XML (contains Microsoft Word namespace)
        if "schemas.microsoft.com/office/word" in raw:
            return _parse_word_xml_codes(raw)

        tree = ET.parse(path)
        root = tree.getroot()

        for game in root.iter("game"):
            for code in game.iter("code"):
                name = code.get("name", "")
                text = (code.text or "").strip()
                parsed = _parse_code_lines(text, name)
                discoveries.extend(parsed)

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


def _parse_word_xml_codes(raw: str) -> list[dict]:
    """Extract cheat codes from a Word 2003 XML document.

    Extracts text content, identifies labeled code sections,
    and parses CodeBreaker/Action Replay format codes.
    """
    # Extract all text content from Word XML
    # Text is in <w:t> tags
    text_parts = re.findall(r'<w:t[^>]*>(.*?)</w:t>', raw)
    full_text = "\n".join(text_parts)

    discoveries = []
    current_label = ""
    lines = full_text.splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if this is a code line (8 hex + space + 4-8 hex)
        code_match = re.match(r'^([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{4,8})$', line)
        if code_match:
            parsed = _parse_code_lines(line, current_label)
            discoveries.extend(parsed)
        else:
            # Treat as potential label (skip very short or numeric-only lines)
            cleaned = line.strip()
            if cleaned and len(cleaned) > 2 and not re.match(r'^[0-9A-Fa-f\s]+$', cleaned):
                current_label = cleaned

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

    Only handles unencrypted CodeBreaker codes:
    - Type 3: 16-bit constant write (3XXXXXXX YYYY)
    - Type 8: 8-bit constant write (8XXXXXXX 00YY)
    - Type 0: 32-bit constant write (0XXXXXXX YYYYYYYY)

    Encrypted codes (AR v3, random-looking hex) are skipped —
    those need the knowledge analysis agent to decrypt.
    """
    discoveries = []

    for line in text.splitlines():
        line = line.strip()
        match = re.match(r'^([0-9A-Fa-f]{8})[\s:]([0-9A-Fa-f]{4,8})', line)
        if not match:
            continue

        raw_addr = match.group(1)
        value = match.group(2)

        code_type = int(raw_addr[0], 16)
        address_offset = int(raw_addr[1:], 16)

        # Only accept known unencrypted CodeBreaker types
        # with addresses in valid GBA IWRAM/EWRAM range
        if code_type == 3 and address_offset < 0x8000:
            address = f"0x{0x03000000 + address_offset:08x}"
            data_type = "u16"
        elif code_type == 8 and address_offset < 0x8000:
            address = f"0x{0x03000000 + address_offset:08x}"
            data_type = "u8"
        elif code_type == 0 and address_offset < 0x40000:
            address = f"0x{0x02000000 + address_offset:08x}"
            data_type = "u32"
        else:
            # Likely encrypted or unknown format — skip
            continue

        discoveries.append({
            "label": label or f"code_{address}",
            "address": address,
            "data_type": data_type,
            "notes": f"Value: 0x{value} (type {code_type})",
        })

    return discoveries

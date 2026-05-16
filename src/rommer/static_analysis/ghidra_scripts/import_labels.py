# -*- coding: utf-8 -*-
# Ghidra script to import discovery labels from JSON file.
# Run via: analyzeHeadless ... -postScript import_labels.py

import json
import os
import re

from ghidra.program.model.symbol import SourceType
from ghidra.program.model.listing import CodeUnit

label_file = os.environ.get("ROMMER_LABELS_FILE")
if not label_file:
    script_dir = os.path.dirname(sourceFile.getAbsolutePath()) if 'sourceFile' in dir() else os.getcwd()
    label_file = os.path.join(script_dir, "discovery_labels.json")

if not os.path.exists(label_file):
    print("Label file not found: " + label_file)
else:
    f = open(label_file, "r")
    labels = json.load(f)
    f.close()

    symbol_table = currentProgram.getSymbolTable()
    namespace = currentProgram.getGlobalNamespace()
    listing = currentProgram.getListing()

    imported = 0
    skipped = 0

    for entry in labels:
        addr_int = int(entry["address"], 16)
        label = entry["label"]
        # Clean label for Ghidra
        label = re.sub(r'[^a-zA-Z0-9_]', '_', label)
        if not label or label[0].isdigit():
            label = "_" + label

        try:
            addr = toAddr(addr_int)
            symbol_table.createLabel(addr, label, namespace, SourceType.USER_DEFINED)

            data_type = entry.get("data_type", "")
            notes = entry.get("notes", "")
            comment = "[" + data_type + "] " + entry.get("label", "")
            if notes:
                comment = comment + " -- " + notes[:150]
            listing.setComment(addr, CodeUnit.EOL_COMMENT, comment)

            imported += 1
        except Exception as e:
            skipped += 1

    print("Imported " + str(imported) + " labels, skipped " + str(skipped))

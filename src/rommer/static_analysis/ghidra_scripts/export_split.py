# -*- coding: utf-8 -*-
# Ghidra script to export each function as its own .c file.
# Run via: analyzeHeadless ... -noanalysis -postScript export_split.py

import os
import json
import re

from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

base_dir = os.environ.get("ROMMER_OUTPUT_DIR")
if not base_dir:
    base_dir = os.path.join(os.path.dirname(sourceFile.getAbsolutePath()), "decompiled")
output_dir = os.path.join(base_dir, "functions")
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

monitor = ConsoleTaskMonitor()
decomp = DecompInterface()
decomp.openProgram(currentProgram)

func_manager = currentProgram.getFunctionManager()
funcs = func_manager.getFunctions(True)

total = 0
success = 0

print("Exporting individual function files...")

while funcs.hasNext():
    func = funcs.next()
    total += 1

    try:
        result = decomp.decompileFunction(func, 60, monitor)
        if result.decompileCompleted():
            c_code = result.getDecompiledFunction().getC()
            entry = func.getEntryPoint().getOffset()
            name = func.getName()

            # Clean name for filename
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
            filename = "%08X_%s.c" % (entry, safe_name)

            filepath = os.path.join(output_dir, filename)
            f = open(filepath, "w")
            f.write("// Function: %s\n" % name)
            f.write("// Address:  0x%08X\n" % entry)
            f.write("// Size:     %d bytes\n\n" % func.getBody().getNumAddresses())
            f.write(c_code)
            f.close()

            success += 1
    except:
        pass

    if total % 500 == 0:
        print("  %d / ? functions exported (%d success)" % (total, success))

print("")
print("Done! %d functions exported to %s" % (success, output_dir))

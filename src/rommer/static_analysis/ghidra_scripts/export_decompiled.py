# -*- coding: utf-8 -*-
# Ghidra script to export decompiled C code for all functions.
# Run via: analyzeHeadless ... -postScript export_decompiled.py

import os
import json

from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

output_dir = os.environ.get("ROMMER_OUTPUT_DIR")
if not output_dir:
    output_dir = os.path.join(os.path.dirname(sourceFile.getAbsolutePath()), "decompiled")
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

monitor = ConsoleTaskMonitor()
decomp = DecompInterface()
decomp.openProgram(currentProgram)

func_manager = currentProgram.getFunctionManager()
funcs = func_manager.getFunctions(True)

total = 0
success = 0
failed = 0
all_code = []
func_index = []

print("Decompiling all functions...")

while funcs.hasNext():
    func = funcs.next()
    total += 1

    try:
        result = decomp.decompileFunction(func, 60, monitor)
        if result.decompileCompleted():
            c_code = result.getDecompiledFunction().getC()
            entry = func.getEntryPoint().getOffset()
            name = func.getName()

            all_code.append("// Function: " + name + " @ 0x" + format(entry, "08X"))
            all_code.append("// Size: " + str(func.getBody().getNumAddresses()) + " bytes")
            all_code.append(c_code)
            all_code.append("")

            func_index.append({
                "name": name,
                "address": "0x" + format(entry, "08X"),
                "size": func.getBody().getNumAddresses(),
            })

            success += 1
        else:
            failed += 1
    except Exception as e:
        failed += 1

    if total % 100 == 0:
        print("  Processed " + str(total) + " functions (" + str(success) + " decompiled)...")

# Write single combined C file
combined_path = os.path.join(output_dir, "all_functions.c")
f = open(combined_path, "w")
f.write("// Decompiled from: medabots_rpg_rokusho.gba\n")
f.write("// Total functions: " + str(total) + "\n")
f.write("// Successfully decompiled: " + str(success) + "\n\n")
f.write("\n".join(all_code))
f.close()

# Write function index
index_path = os.path.join(output_dir, "function_index.json")
f = open(index_path, "w")
json.dump(func_index, f, indent=2)
f.close()

# Also export labeled addresses with their xrefs
symbol_table = currentProgram.getSymbolTable()
ref_manager = currentProgram.getReferenceManager()
labeled = []

symbols = symbol_table.getAllSymbols(True)
while symbols.hasNext():
    sym = symbols.next()
    if sym.getSource().toString() == "USER_DEFINED":
        addr = sym.getAddress()
        refs = ref_manager.getReferencesTo(addr)
        xrefs = []
        for ref in refs:
            from_addr = ref.getFromAddress()
            from_func = func_manager.getFunctionContaining(from_addr)
            xrefs.append({
                "from": "0x" + format(from_addr.getOffset(), "08X"),
                "function": from_func.getName() if from_func else None,
                "type": str(ref.getReferenceType()),
            })
        labeled.append({
            "name": sym.getName(),
            "address": "0x" + format(addr.getOffset(), "08X"),
            "xref_count": len(xrefs),
            "xrefs": xrefs,
        })

xref_path = os.path.join(output_dir, "label_xrefs.json")
f = open(xref_path, "w")
json.dump(labeled, f, indent=2)
f.close()

print("")
print("Done!")
print("  Functions: " + str(total) + " total, " + str(success) + " decompiled, " + str(failed) + " failed")
print("  Labeled symbols with xrefs: " + str(len(labeled)))
print("  Output: " + output_dir)

# -*- coding: utf-8 -*-
# Ghidra script to set up GBA memory map for ROM imported at 0x08000000.
# Adds IWRAM/EWRAM/IO/Palette/VRAM/OAM regions and sets the entry point.
#
# GBA Memory Map:
#   0x02000000-0x0203FFFF  EWRAM (256KB, on-board work RAM)
#   0x03000000-0x03007FFF  IWRAM (32KB, on-chip work RAM)
#   0x04000000-0x040003FF  IO registers
#   0x05000000-0x050003FF  Palette RAM (1KB)
#   0x06000000-0x06017FFF  VRAM (96KB)
#   0x07000000-0x070003FF  OAM (1KB)
#   0x08000000-0x09FFFFFF  ROM (up to 32MB)

from ghidra.program.model.mem import MemoryConflictException

memory = currentProgram.getMemory()

print("Setting up GBA memory map...")

regions = [
    ("EWRAM",   0x02000000, 0x40000, False),
    ("IWRAM",   0x03000000, 0x8000,  False),
    ("IO",      0x04000000, 0x400,   True),
    ("Palette", 0x05000000, 0x400,   False),
    ("VRAM",    0x06000000, 0x18000, False),
    ("OAM",     0x07000000, 0x400,   False),
]

for name, base, size, volatile in regions:
    try:
        block = memory.createUninitializedBlock(name, toAddr(base), size, False)
        block.setRead(True)
        block.setWrite(True)
        block.setExecute(False)
        if volatile:
            block.setVolatile(True)
        print("  Added %s: 0x%08X-0x%08X (%dKB)" % (name, base, base + size - 1, size // 1024))
    except MemoryConflictException:
        print("  %s already exists" % name)
    except Exception as e:
        print("  %s failed: %s" % (name, str(e)))

# Set entry point at ROM start (0x08000000)
# GBA ROM header: first 4 bytes are an ARM branch instruction to the real entry
try:
    entry_addr = toAddr(0x08000000)
    func = currentProgram.getFunctionManager().getFunctionAt(entry_addr)
    if not func:
        from ghidra.app.cmd.function import CreateFunctionCmd
        cmd = CreateFunctionCmd(entry_addr)
        cmd.applyTo(currentProgram, monitor)
        print("  Created entry function at 0x08000000")
    currentProgram.getSymbolTable().addExternalEntryPoint(entry_addr)
    print("  Set entry point at 0x08000000")
except Exception as e:
    print("  Entry point setup: " + str(e))

print("")
print("GBA memory map setup complete.")

# -*- coding: utf-8 -*-
# Ghidra script to set up proper GBA memory map.
# Rebases ROM to 0x08000000 and adds IWRAM/EWRAM regions.

from ghidra.program.model.mem import MemoryConflictException

memory = currentProgram.getMemory()
space = currentProgram.getAddressFactory().getDefaultAddressSpace()

# 1. Rebase ROM from 0x00000000 to 0x08000000
rom_block = memory.getBlock(toAddr(0x00000000))
if rom_block:
    print("Moving ROM block to 0x08000000...")
    try:
        memory.moveBlock(rom_block, toAddr(0x08000000), monitor)
        print("  ROM rebased to 0x08000000")
    except Exception as e:
        print("  Rebase failed: " + str(e))
        print("  ROM may already be at correct address")

# 2. Add IWRAM region (0x03000000 - 0x03007FFF, 32KB)
try:
    iwram = memory.createUninitializedBlock("IWRAM", toAddr(0x03000000), 0x8000, False)
    iwram.setRead(True)
    iwram.setWrite(True)
    iwram.setExecute(False)
    print("  Added IWRAM: 0x03000000-0x03007FFF (32KB)")
except MemoryConflictException:
    print("  IWRAM already exists")
except Exception as e:
    print("  IWRAM failed: " + str(e))

# 3. Add EWRAM region (0x02000000 - 0x0203FFFF, 256KB)
try:
    ewram = memory.createUninitializedBlock("EWRAM", toAddr(0x02000000), 0x40000, False)
    ewram.setRead(True)
    ewram.setWrite(True)
    ewram.setExecute(False)
    print("  Added EWRAM: 0x02000000-0x0203FFFF (256KB)")
except MemoryConflictException:
    print("  EWRAM already exists")
except Exception as e:
    print("  EWRAM failed: " + str(e))

# 4. Add IO registers (0x04000000 - 0x040003FF)
try:
    io = memory.createUninitializedBlock("IO", toAddr(0x04000000), 0x400, False)
    io.setRead(True)
    io.setWrite(True)
    io.setExecute(False)
    io.setVolatile(True)
    print("  Added IO: 0x04000000-0x040003FF")
except MemoryConflictException:
    print("  IO already exists")
except Exception as e:
    print("  IO failed: " + str(e))

# 5. Add VRAM (0x06000000 - 0x06017FFF, 96KB)
try:
    vram = memory.createUninitializedBlock("VRAM", toAddr(0x06000000), 0x18000, False)
    vram.setRead(True)
    vram.setWrite(True)
    vram.setExecute(False)
    print("  Added VRAM: 0x06000000-0x06017FFF (96KB)")
except MemoryConflictException:
    print("  VRAM already exists")
except Exception as e:
    print("  VRAM failed: " + str(e))

# 6. Add OAM (0x07000000 - 0x070003FF, 1KB)
try:
    oam = memory.createUninitializedBlock("OAM", toAddr(0x07000000), 0x400, False)
    oam.setRead(True)
    oam.setWrite(True)
    oam.setExecute(False)
    print("  Added OAM: 0x07000000-0x070003FF (1KB)")
except MemoryConflictException:
    print("  OAM already exists")
except Exception as e:
    print("  OAM failed: " + str(e))

print("")
print("Memory map setup complete. Re-run analysis to resolve new references.")

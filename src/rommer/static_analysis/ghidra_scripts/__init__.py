"""Ghidra Jython scripts for headless analysis.

These scripts are designed to run inside Ghidra's Jython environment
via analyzeHeadless -postScript. They use Ghidra's Java API directly.

Scripts:
- setup_memory.py: Set up GBA memory map (rebase ROM, add IWRAM/EWRAM/etc)
- import_labels.py: Import discovery labels from JSON
- export_decompiled.py: Decompile all functions, export combined + index
- export_split.py: Export each function as individual .c file
"""

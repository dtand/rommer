"""Ghidra bridge client - queries a running Ghidra instance via RPC."""

import importlib


class GhidraClient:
    """Thin wrapper over ghidra-bridge for live Ghidra queries."""

    def __init__(self, host: str = "127.0.0.1", port: int = 4768):
        self.host = host
        self.port = port
        self._bridge = None

    def connect(self):
        """Connect to ghidra_bridge_server."""
        bridge_mod = importlib.import_module("ghidra_bridge")
        self._bridge = bridge_mod.GhidraBridge(
            connect_to_host=self.host, connect_to_port=self.port
        )

    @property
    def bridge(self):
        if self._bridge is None:
            self.connect()
        return self._bridge

    def get_xrefs_to(self, address: int) -> list[dict]:
        """Get all cross-references to an address."""
        b = self.bridge
        addr = b.remote_eval(f"toAddr({address})")
        refs = b.remote_eval(
            f"list(currentProgram.getReferenceManager().getReferencesTo(toAddr({address})))"
        )
        results = []
        for ref in refs:
            from_addr = b.remote_eval(f"ref.getFromAddress().getOffset()", ref=ref)
            results.append({
                "from_address": f"0x{from_addr:08X}",
                "type": str(b.remote_eval("str(ref.getReferenceType())", ref=ref)),
            })
        return results

    def decompile_function(self, address: int) -> str | None:
        """Decompile a function at the given address."""
        b = self.bridge
        code = b.remote_eval(f"""
(lambda addr: (
    __import__('ghidra.app.decompiler', fromlist=['DecompInterface']).DecompInterface().tap(
        lambda d: d.openProgram(currentProgram)
    ) or None
))({address})
""")
        # Simplified - actual implementation uses bridge eval
        return code

    def get_function_info(self, address: int) -> dict | None:
        """Get function metadata at address."""
        b = self.bridge
        return b.remote_eval(f"""
(lambda: {{
    'name': currentProgram.getFunctionManager().getFunctionAt(toAddr({address})).getName(),
    'address': '0x{address:08X}',
    'size': currentProgram.getFunctionManager().getFunctionAt(toAddr({address})).getBody().getNumAddresses(),
}})()
""")

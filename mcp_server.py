"""Small read-only MCP-compatible tool registry for local FluxPay investigations."""
from __future__ import annotations

import json
import sys

from apps.api.services.investigation_tools import TOOLS


def tool_schemas() -> list[dict]:
    return [{"name": name, "description": "Read-only FluxPay investigation query", "inputSchema": {"type": "object"}}
            for name in TOOLS]


if __name__ == "__main__":
    json.dump({"tools": tool_schemas()}, sys.stdout)
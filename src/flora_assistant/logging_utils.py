"""Console + file logging for every MCP request/response the host makes."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger("flora_assistant.mcp")
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())
logger.addHandler(logging.FileHandler("mcp_interactions.log", encoding="utf-8"))


def log_mcp_call(
    server_name: str,
    tool_name: str,
    payload: Any,
    phase: Literal["request", "response"],
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": server_name,
        "tool": tool_name,
        "phase": phase,
        "payload": str(payload),
    }
    logger.info(json.dumps(entry, ensure_ascii=False))

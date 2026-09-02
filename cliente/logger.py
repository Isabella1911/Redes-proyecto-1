import json
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(__file__).parent / "mcp_interactions.log"

def log_mcp_interaction(tool_name: str, params: dict, result, server_name: str = "unknown"):
    """Registra cada solicitud/respuesta a servidores MCP (Fase 1, req. 3)."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "server": server_name,
        "tool": tool_name,
        "params": params,
        "result": str(result)[:500],  # truncado por si la respuesta es larga
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[LOG] {server_name}.{tool_name}({params}) -> {str(result)[:100]}")
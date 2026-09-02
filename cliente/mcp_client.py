import json
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from logger import log_mcp_interaction


class MCPManager:
    """Mantiene conexiones a múltiples servidores MCP y expone sus tools."""

    def __init__(self, config_path: str = "mcp_servers.json"):
        self.config_path = Path(__file__).parent / config_path
        self.sessions: dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        # tool_name (con prefijo servidor) -> (server_name, tool_original_name)
        self.tool_routing: dict[str, tuple[str, str]] = {}

    async def connect_all(self):
        config = json.loads(self.config_path.read_text())

        for server_cfg in config["servers"]:
            name = server_cfg["name"]
            params = StdioServerParameters(
                command=server_cfg["command"],
                args=server_cfg["args"],
                env=server_cfg.get("env"),
            )

            read, write = await self.exit_stack.enter_async_context(stdio_client(params))
            session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            self.sessions[name] = session
            print(f"[MCP] Conectado a servidor '{name}'")

    async def list_all_tools_for_anthropic(self) -> list[dict]:
        """Convierte las tools de todos los servidores al formato que espera la API de Anthropic."""
        anthropic_tools = []

        for server_name, session in self.sessions.items():
            result = await session.list_tools()
            for tool in result.tools:
                # Prefijamos con el nombre del servidor para evitar colisiones de nombres
                prefixed_name = f"{server_name}__{tool.name}"
                self.tool_routing[prefixed_name] = (server_name, tool.name)

                anthropic_tools.append({
                    "name": prefixed_name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema,
                })

        return anthropic_tools

    async def call_tool(self, prefixed_name: str, arguments: dict):
        server_name, original_name = self.tool_routing[prefixed_name]
        session = self.sessions[server_name]

        result = await session.call_tool(original_name, arguments)
        content = result.content[0].text if result.content else ""

        log_mcp_interaction(
            tool_name=original_name,
            params=arguments,
            result=content,
            server_name=server_name,
        )
        return content

    async def close(self):
        await self.exit_stack.aclose()
"""Conversation loop: keeps message history and drives the Claude tool-use cycle."""

import os

from anthropic import Anthropic

from .mcp_manager import MCPManager

# Overridable so a key without access to the newest model can fall back
# (e.g. ANTHROPIC_MODEL=claude-sonnet-4-5) without touching the code.
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOKENS = 2048

SYSTEM_PROMPT = """\
Eres un asistente de flora que ayuda a identificar plantas a partir de fotos y a \
determinar si una especie es nativa, introducida o invasora en el lugar donde se \
encuentra la persona.

Como trabajas:
- Si el usuario menciona una foto, usa primero la herramienta de identificacion y \
  reporta siempre la confianza que devuelve. Si hay varios candidatos con confianza \
  parecida, dilos todos en vez de escoger uno solo.
- Necesitas saber en que pais esta la persona para clasificar la especie. Si no lo \
  ha dicho, preguntaselo antes de clasificar; no lo asumas.
- Para el estatus (nativa / introducida / invasora) usa siempre las herramientas. \
  Nunca lo respondas de memoria: la respuesta depende del pais y cambia entre paises.
- Cita la evidencia que devuelve la herramienta (el campo `basis`, el checklist \
  nacional, GRIIS, GISD o el numero de registros de GBIF). Si el estatus es \
  "presente, estatus no documentado" o "sin registros", dilo tal cual en vez de \
  inventar una conclusion.
- Si la especie resulta invasora o introducida, ofrece las recomendaciones de manejo. \
  Si no hay recomendaciones curadas para esa especie, dilo en lugar de improvisarlas.
- Puedes leer y escribir archivos en la carpeta de trabajo y versionar reportes con \
  git cuando el usuario lo pida.

Responde en el idioma en que te escriban, de forma breve y concreta.
"""


class Chatbot:
    def __init__(self, mcp_manager: MCPManager) -> None:
        self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.mcp = mcp_manager
        self.history: list[dict] = []
        # Tool calls made while answering the most recent message, for callers
        # (e.g. the web UI) that want to show what was used.
        self.last_tool_calls: list[dict] = []

    async def send(self, user_message: str) -> str:
        self.last_tool_calls = []
        self.history.append({"role": "user", "content": user_message})
        tools = await self.mcp.list_all_tools()

        while True:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=self.history,
                tools=tools,
            )
            self.history.append({"role": "assistant", "content": response.content})

            tool_uses = [block for block in response.content if block.type == "tool_use"]
            if not tool_uses:
                return "".join(
                    block.text for block in response.content if block.type == "text"
                )

            tool_results = []
            for block in tool_uses:
                result_text = await self.mcp.call_tool(block.name, block.input)
                # Show the tool under its own name, not the server-qualified one
                # Claude was given -- the server is already its own column.
                server_name, bare_name = self.mcp.tool_routing.get(
                    block.name, ("?", block.name)
                )
                self.last_tool_calls.append(
                    {"server": server_name, "tool": bare_name, "arguments": block.input}
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    }
                )
            self.history.append({"role": "user", "content": tool_results})

    def reset(self) -> None:
        """Drop the conversation history, keeping the connected servers."""
        self.history = []
        self.last_tool_calls = []

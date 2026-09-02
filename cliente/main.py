import asyncio
import os
from dotenv import load_dotenv
from anthropic import Anthropic

from mcp_client import MCPManager

load_dotenv()
MODEL = "claude-sonnet-4-6"


class Chatbot:
    def __init__(self, mcp_manager: MCPManager):
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.messages = []
        self.mcp = mcp_manager
        self.tools = []

    async def load_tools(self):
        self.tools = await self.mcp.list_all_tools_for_anthropic()
        print(f"[Chatbot] {len(self.tools)} herramientas MCP disponibles.\n")

    async def ask(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})

        while True:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=1024,
                messages=self.messages,
                tools=self.tools,
            )

            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                # Respuesta final en texto
                text_blocks = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_blocks)

            # Claude pidió usar una o más tools: ejecutarlas y devolver los resultados
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result_text = await self.mcp.call_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    })

            self.messages.append({"role": "user", "content": tool_results})
            # vuelve al inicio del while: Claude ve el resultado y decide si sigue o responde

    def reset(self):
        self.messages = []


async def main():
    mcp = MCPManager()
    await mcp.connect_all()

    bot = Chatbot(mcp)
    await bot.load_tools()

    print("Chatbot MCP - Fase 2 (Filesystem + Git)")
    print("Escribe 'salir' para terminar, 'reset' para limpiar contexto.\n")

    try:
        while True:
            user_input = input("Tú: ").strip()
            if user_input.lower() == "salir":
                break
            if user_input.lower() == "reset":
                bot.reset()
                print("[Contexto reiniciado]\n")
                continue
            if not user_input:
                continue

            try:
                reply = await bot.ask(user_input)
                print(f"\nAsistente: {reply}\n")
            except Exception as e:
                print(f"[ERROR] {e}\n")
    finally:
        await mcp.close()


if __name__ == "__main__":
    asyncio.run(main())
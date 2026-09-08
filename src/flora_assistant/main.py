"""Entry point: console REPL for the flora assistant chatbot."""

import asyncio
import sys

from dotenv import load_dotenv

from .chatbot import Chatbot
from .mcp_manager import MCPManager

BANNER = """\
Asistente de flora -- identifica plantas y su estatus (nativa / introducida / invasora).
Comandos: 'salir' para terminar, 'reset' para limpiar el contexto.
"""


async def run_async() -> None:
    load_dotenv()
    mcp_manager = MCPManager()
    await mcp_manager.connect_all()
    chatbot = Chatbot(mcp_manager)

    print(BANNER)
    # With several servers configured -- two of them other people's, possibly
    # over the network -- which ones actually came up is the first thing worth
    # knowing. The web UI shows this in the sidebar; the REPL has to say it.
    tools = await mcp_manager.list_all_tools()
    connected = ", ".join(mcp_manager.sessions) or "ninguno"
    print(f"Servidores conectados ({len(mcp_manager.sessions)}): {connected}")
    print(f"Herramientas disponibles: {len(tools)}")
    for name, reason in mcp_manager.startup_errors.items():
        print(f"  [!] '{name}' no conecto -- {reason}")
    print()
    try:
        while True:
            try:
                user_input = input("tu> ")
            except (EOFError, KeyboardInterrupt):
                # Ctrl+C, Ctrl+Z, or piped input running out. All three mean
                # "done" -- ending on a stack trace would just look like a crash.
                print()
                break

            # PowerShell prefixes a BOM when piping text into a program, so a
            # scripted `echo salir | flora-assistant` would otherwise be sent to
            # Claude as a message instead of quitting.
            user_input = user_input.strip().lstrip("﻿").strip()

            if user_input.lower() in {"salir", "exit", "quit"}:
                break
            if user_input.lower() == "reset":
                chatbot.reset()
                print("[contexto reiniciado]")
                continue
            if not user_input:
                continue

            try:
                reply = await chatbot.send(user_input)
                print(f"asistente> {reply}\n")
            except Exception as exc:  # noqa: BLE001 -- keep the REPL alive
                print(f"[error] {exc}\n")
    finally:
        await mcp_manager.close()


def run() -> None:
    # Windows consoles default to a legacy codepage (e.g. cp1252) that cannot
    # encode accents or emoji Claude's replies may include; force UTF-8 so a
    # print() does not crash the session over a glyph.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    asyncio.run(run_async())


if __name__ == "__main__":
    run()

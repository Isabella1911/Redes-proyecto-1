"""Owns one MCP ClientSession per configured server and routes tool calls."""

import asyncio
from contextlib import AsyncExitStack, suppress
from typing import Any
from urllib.parse import urlparse

import httpx2
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from .config import HTTP_SERVERS, STDIO_SERVERS
from .logging_utils import log_mcp_call

# How long to wait for a remote server's TCP connection before giving up.
# Without this, an unreachable peer (wrong IP, firewall dropping packets, server
# not started) blocks startup on the OS-level timeout -- around 20 seconds per
# server on Windows, which with several classmates' servers configured turns a
# demo into a wait. Five seconds is plenty on a LAN.
REMOTE_CONNECT_TIMEOUT = 5.0


def remote_http_client() -> httpx2.AsyncClient:
    """An HTTP client that fails fast on connect but never on read.

    MCP keeps a long-lived response stream open for server-to-client messages,
    so a read deadline would kill a working session mid-conversation. Only the
    connect phase gets a deadline.
    """
    return httpx2.AsyncClient(
        timeout=httpx2.Timeout(
            connect=REMOTE_CONNECT_TIMEOUT, read=None, write=30.0, pool=30.0
        )
    )


async def reachable(url: str, timeout: float = REMOTE_CONNECT_TIMEOUT) -> bool:
    """Can we even open a TCP connection to this server?

    Checked before the MCP handshake because an unreachable peer is the normal
    case on a shared network -- someone's laptop is asleep, or their firewall is
    dropping the port -- and a failed handshake leaves half-open streams that
    are far more awkward to unwind than a connection never attempted.
    """
    parsed = urlparse(url)
    if not parsed.hostname:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        async with asyncio.timeout(timeout):
            _, writer = await asyncio.open_connection(parsed.hostname, port)
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
        return True
    except (OSError, TimeoutError):
        return False


def exposed_name(server_name: str, tool_name: str) -> str:
    """The name Claude sees for a tool: the server's name, then the tool's.

    Two servers can legitimately publish the same tool name -- most obviously
    this project's own server reached both locally over stdio and remotely over
    HTTP, but any two people's servers might both call something `search`.
    Without a namespace the second registration silently replaces the first, and
    the model is handed a tool list with duplicate names.

    Anthropic requires tool names to match ^[a-zA-Z0-9_-]{1,128}$, which both
    halves and the separator satisfy.
    """
    return f"{server_name}__{tool_name}"


class MCPManager:
    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self.sessions: dict[str, ClientSession] = {}
        # exposed name -> (server name, the tool's own name on that server)
        self.tool_routing: dict[str, tuple[str, str]] = {}
        # Servers that failed to start, name -> reason. The demo connects to
        # five servers, two of them other people's, so one being unavailable
        # (a classmate's MySQL not running, say) must not take the chatbot
        # down with it -- the rest of the tools still work.
        self.startup_errors: dict[str, str] = {}

    async def _register(self, name: str, read: Any, write: Any) -> None:
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._register_session(name, session)

    async def _register_session(self, name: str, session: Any) -> None:
        """Initialise a session and index its tools. Split out from _register so
        the routing can be tested without a real transport."""
        await session.initialize()
        self.sessions[name] = session

        listed = await session.list_tools()
        for tool in listed.tools:
            self.tool_routing[exposed_name(name, tool.name)] = (name, tool.name)

    async def connect_all(self) -> None:
        for cfg in STDIO_SERVERS:
            params = StdioServerParameters(
                command=cfg.command, args=cfg.args, env=cfg.env or None, cwd=cfg.cwd
            )
            try:
                read, write = await self._stack.enter_async_context(stdio_client(params))
                await self._register(cfg.name, read, write)
            except Exception as exc:  # noqa: BLE001 -- one bad server must not stop the rest
                self.startup_errors[cfg.name] = f"{type(exc).__name__}: {exc}"

        for http_cfg in HTTP_SERVERS:
            if not await reachable(http_cfg.url):
                self.startup_errors[http_cfg.name] = (
                    f"inalcanzable en {http_cfg.url} "
                    f"(sin respuesta TCP en {REMOTE_CONNECT_TIMEOUT:.0f}s)"
                )
                continue

            # Each remote gets its own stack for the handshake. A server that
            # accepts TCP but then fails or stalls leaves half-open streams
            # behind, and unwinding those from the shared stack can deadlock on
            # the anyio issue described in close(). Here a failure is torn down
            # on its own, and only a fully working session is handed over to the
            # shared stack.
            attempt = AsyncExitStack()
            try:
                client = await attempt.enter_async_context(remote_http_client())
                read, write = await attempt.enter_async_context(
                    streamable_http_client(http_cfg.url, http_client=client)
                )
                session = await attempt.enter_async_context(ClientSession(read, write))
                await self._register_session(http_cfg.name, session)
                await self._stack.enter_async_context(attempt.pop_all())
            except Exception as exc:  # noqa: BLE001
                self.startup_errors[http_cfg.name] = f"{type(exc).__name__}: {exc}"
                with suppress(Exception, asyncio.CancelledError):
                    async with asyncio.timeout(REMOTE_CONNECT_TIMEOUT):
                        await attempt.aclose()

    async def list_all_tools(self) -> list[dict[str, Any]]:
        """Every tool from every server, named for Claude (server-qualified)."""
        all_tools: list[dict[str, Any]] = []
        for server_name, session in self.sessions.items():
            listed = await session.list_tools()
            for tool in listed.tools:
                all_tools.append(
                    {
                        "name": exposed_name(server_name, tool.name),
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                    }
                )
        return all_tools

    async def list_tools_by_server(self) -> list[dict[str, Any]]:
        """Tools grouped by the server that provides them, for UIs that want to
        show a per-server checklist rather than one flat list.

        Tools keep their own names here: the group header already says which
        server they came from, so repeating it in every row would be noise.
        Servers that failed to start are included with an `error`, so the UI can
        show them as down instead of silently omitting them.
        """
        grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in self.sessions}
        for server_name, session in self.sessions.items():
            listed = await session.list_tools()
            grouped[server_name] = [
                {"name": tool.name, "description": tool.description} for tool in listed.tools
            ]

        servers = [{"name": name, "tools": tools} for name, tools in grouped.items()]
        servers += [
            {"name": name, "tools": [], "error": reason}
            for name, reason in self.startup_errors.items()
        ]
        return servers

    async def call_tool(self, exposed: str, arguments: dict[str, Any]) -> str:
        server_name, tool_name = self.tool_routing[exposed]
        session = self.sessions[server_name]

        log_mcp_call(server_name, tool_name, arguments, phase="request")
        result = await session.call_tool(tool_name, arguments)
        log_mcp_call(server_name, tool_name, result, phase="response")

        text = "\n".join(block.text for block in result.content if block.type == "text")
        if result.is_error:
            return f"Error: {text}" if text else "Error: tool call failed"
        return text

    async def close(self) -> None:
        try:
            await self._stack.aclose()
        except Exception:
            # Known anyio/MCP SDK teardown ordering issue when several
            # subprocess-backed stdio clients share one AsyncExitStack
            # (modelcontextprotocol/python-sdk issues #79, #521, #577): cancel
            # scopes must exit in the task that entered them, which does not
            # always hold with multiple stdio clients. Harmless -- every session
            # is done with its real work by the time close() runs -- so a noisy
            # teardown error should not look like a failed run.
            pass

"""Configuration for the MCP servers this host connects to."""

import os
import sys
from dataclasses import dataclass, field


@dataclass
class StdioServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    # Merged over the MCP SDK's own safe-by-default env (PATH, SYSTEMROOT, ...).
    # Keep this empty unless a server genuinely needs something extra -- do not
    # widen it to the full parent environment, since that would also hand the
    # subprocess ANTHROPIC_API_KEY and anything else this process holds.
    env: dict[str, str] = field(default_factory=dict)
    # Working directory to launch the server in, relative to this repo's root.
    # Needed by servers whose module resolution depends on cwd (Python's
    # `-m package.module`, a Node project's relative source paths) rather than
    # taking an explicit directory argument.
    cwd: str | None = None


@dataclass
class HttpServerConfig:
    name: str
    url: str


# Local servers, launched as subprocesses and spoken to over stdio.
STDIO_SERVERS: list[StdioServerConfig] = [
    StdioServerConfig(
        name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "./workspace"],
    ),
    StdioServerConfig(
        name="git",
        command="uvx",
        args=["mcp-server-git"],
    ),
    StdioServerConfig(
        name="flora",
        # sys.executable, not a bare "python": the server lives in this repo and
        # must run in the same virtualenv the host does, whatever launched it.
        command=sys.executable,
        args=["-m", "flora_mcp.server"],
    ),
    # Classmates' servers (rubric item 6). Cloned under ../Proyecto1_Redes/;
    # each one has its own README for setup. A server that is not installed or
    # whose backing service is down is reported in MCPManager.startup_errors and
    # skipped, so the chatbot still runs without them.
    StdioServerConfig(
        name="docfinder",
        command="npx",
        args=["tsx", "src/index.ts"],
        cwd="../Proyecto1_Redes/CC3067-Proyecto1-docfinder",
    ),
    StdioServerConfig(
        name="library",
        # Its own virtualenv, not ours: it needs pymysql, which this project
        # does not depend on.
        command="../Proyecto1_Redes/CC3067-library-mcp/.venv/Scripts/python.exe",
        args=["-m", "mcp_servers.local_library.server"],
        cwd="../Proyecto1_Redes/CC3067-library-mcp",
    ),
]

def remote_servers_from_env() -> list[HttpServerConfig]:
    """Remote servers declared in FLORA_REMOTE_MCP, so pointing the host at a
    deployed server (yours or a classmate's) is an .env change, not a code
    change -- which matters when the URL is only known at demo time.

    Format: comma-separated URLs, each optionally prefixed with a name.

        FLORA_REMOTE_MCP=https://flora.example.com/mcp
        FLORA_REMOTE_MCP=flora-remoto=http://10.0.0.5:8100/mcp,compa=https://x/mcp
    """
    servers: list[HttpServerConfig] = []
    for index, entry in enumerate(os.environ.get("FLORA_REMOTE_MCP", "").split(","), start=1):
        entry = entry.strip()
        if not entry:
            continue
        name, separator, url = entry.partition("=")
        if not separator or "://" in name:
            # No name given, so the whole entry is the URL. The "://" check
            # matters for a bare URL carrying a query string: partitioning
            # "https://x/mcp?a=b" on "=" would otherwise mistake "https://x/mcp?a"
            # for a name.
            name, url = f"remoto{index}", entry
        servers.append(HttpServerConfig(name=name.strip(), url=url.strip()))
    return servers


# Remote servers reached over Streamable HTTP (rubric item 7). Add entries here
# for a permanently deployed server, or set FLORA_REMOTE_MCP for an ad-hoc one;
# MCPManager connects to both the same way it connects to a local server.
HTTP_SERVERS: list[HttpServerConfig] = remote_servers_from_env()

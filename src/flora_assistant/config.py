"""Configuration for the MCP servers this host connects to.

The server lists are **functions**, not module-level constants, and that matters:
this module is imported before `main.py` / `web.py` call `load_dotenv()`, so
anything read from the environment at import time would miss the `.env`
entirely. Building the lists at connect time is what makes `FLORA_REMOTE_MCP`
and `PLANTNET_API_KEY` work from a `.env` file at all.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

# This file is src/flora_assistant/config.py, so the repo root is two levels up.
REPO_ROOT = Path(__file__).resolve().parents[2]

# The plant server lives in its own public repository -- it is a deliverable in
# its own right, and other people are meant to clone and run it. Override with
# FLORA_MCP_DIR if you keep it somewhere else.
FLORA_MCP_DIR = Path(
    os.environ.get(
        "FLORA_MCP_DIR", REPO_ROOT.parent / "Proyecto-Redes-Isa" / "flora-remote-mcp"
    )
)


@dataclass
class StdioServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    # Merged over the MCP SDK's own safe-by-default env (PATH, SYSTEMROOT, ...).
    # Keep this to what a server genuinely needs -- do not widen it to the full
    # parent environment, since that would also hand the subprocess
    # ANTHROPIC_API_KEY and anything else this process holds.
    env: dict[str, str] = field(default_factory=dict)
    # Working directory to launch the server in. Needed by servers whose module
    # resolution depends on cwd (Python's `-m package.module`, a Node project's
    # relative source paths) rather than taking an explicit directory argument.
    cwd: str | None = None


@dataclass
class HttpServerConfig:
    name: str
    url: str


def stdio_servers() -> list[StdioServerConfig]:
    """Local servers, launched as subprocesses and spoken to over stdio."""
    return [
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
            # `uv run --directory` launches the server from its own repository
            # using its own virtualenv, so this project does not have to install
            # it -- the same way any other person's server is used.
            command="uv",
            args=["run", "--directory", str(FLORA_MCP_DIR), "flora-mcp"],
            env={
                # The server now runs with its own repo as the working
                # directory, so a relative image name would resolve against
                # *its* workspace, not ours. Point it back here, absolutely.
                "FLORA_IMAGES_DIR": os.environ.get(
                    "FLORA_IMAGES_DIR", str(REPO_ROOT / "workspace")
                ),
                # Hand it the one key it needs, and nothing else.
                "PLANTNET_API_KEY": os.environ.get("PLANTNET_API_KEY", ""),
            },
        ),
        # Classmates' servers (rubric item 6). Cloned under ../Proyecto1_Redes/;
        # each one has its own README for setup. A server that is not installed
        # or whose backing service is down is reported in
        # MCPManager.startup_errors and skipped, so the chatbot still runs.
        StdioServerConfig(
            name="docfinder",
            command="npx",
            args=["tsx", "src/index.ts"],
            cwd="../Proyecto1_Redes/CC3067-Proyecto1-docfinder",
        ),
        StdioServerConfig(
            name="library",
            # Its own virtualenv, not ours: it needs pymysql, which this
            # project does not depend on.
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


def http_servers() -> list[HttpServerConfig]:
    """Remote servers reached over Streamable HTTP (rubric item 7). Declared in
    FLORA_REMOTE_MCP; add permanent ones to the list below."""
    return [*remote_servers_from_env()]

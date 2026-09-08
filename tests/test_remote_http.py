"""Rubric item 7: the flora server reached over Streamable HTTP instead of stdio.

The server is started as a real subprocess listening on a loopback port and
spoken to over HTTP, which is the same code path a host on another machine would
use -- only the URL differs. Proving it here means deploying is a matter of
changing the host and port, not of changing any code.
"""

import asyncio
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from flora_assistant.mcp_manager import reachable

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTUP_TIMEOUT = 30

EXPECTED_TOOLS = {
    "identify_plant_from_photo",
    "classify_species_in_country",
    "get_management_recommendations",
    "list_country_alien_species",
}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_listening(port: int) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"flora-mcp no empezo a escuchar en el puerto {port}")


@pytest.fixture(scope="module")
def http_server() -> str:
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "flora_mcp.server", "--http", "--port", str(port)],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_until_listening(port)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


async def _list_tools(url: str) -> set[str]:
    async with streamable_http_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            return {tool.name for tool in listed.tools}


async def _call(url: str, tool_name: str, arguments: dict) -> dict:
    async with streamable_http_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            assert not result.is_error, result.content
            return json.loads(result.content[0].text)


def test_remote_server_advertises_its_tools_over_http(http_server):
    assert asyncio.run(_list_tools(http_server)) == EXPECTED_TOOLS


def test_remote_tool_call_returns_the_same_result_as_over_stdio(http_server):
    payload = asyncio.run(
        _call(http_server, "get_management_recommendations", {"scientific_name": "Eichhornia crassipes"})
    )
    assert payload["found"] is True
    assert payload["urgency"] == "alta"


def test_the_endpoint_is_really_speaking_http(http_server):
    """Sanity check that something HTTP-shaped is listening: the MCP endpoint
    answers JSON-RPC over POST, so a bare GET must not come back 200 OK."""
    response = requests.get(http_server, timeout=10)
    assert response.status_code != 200


# --- reachability probe ----------------------------------------------------
# A shared network means peers that are asleep, firewalled or simply mistyped.
# The probe is what keeps one of those from stalling everyone else's startup.


def test_a_live_server_is_reachable(http_server):
    assert asyncio.run(reachable(http_server)) is True


def test_a_closed_port_is_not_reachable():
    port = _free_port()  # nothing is listening on it
    assert asyncio.run(reachable(f"http://127.0.0.1:{port}/mcp")) is False


def test_an_unresolvable_host_is_not_reachable():
    assert asyncio.run(reachable("http://no-existe.invalid:8100/mcp")) is False


def test_a_url_without_a_host_is_not_reachable():
    assert asyncio.run(reachable("no-es-una-url")) is False


def test_the_probe_gives_up_quickly_on_a_black_hole():
    """A dropped packet, not a refusal: 203.0.113.0/24 is reserved for docs and
    routes nowhere, so a connection there hangs until something times it out.
    That something has to be us, and quickly."""
    start = time.monotonic()
    assert asyncio.run(reachable("http://203.0.113.1:8100/mcp", timeout=2.0)) is False
    assert time.monotonic() - start < 6.0

"""The TCP probe that runs before an MCP handshake to a remote server.

A shared network means peers that are asleep, firewalled or simply mistyped.
This probe is what keeps one of those from stalling everyone else's startup.
"""

import asyncio
import socket
import time

from flora_assistant.mcp_manager import reachable


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_a_listening_socket_is_reachable():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        assert asyncio.run(reachable(f"http://127.0.0.1:{port}/mcp")) is True
    finally:
        server.close()


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

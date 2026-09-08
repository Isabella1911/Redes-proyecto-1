"""Diagnose MCP connectivity on a LAN, before debugging it through the chatbot.

Two modes:

    python scripts/check_remote_mcp.py
        Show the URLs other people on this network should use to reach your
        flora-mcp server, and whether it is actually listening.

    python scripts/check_remote_mcp.py http://192.168.1.20:8100/mcp [...]
        Check one or more peers, one layer at a time: TCP reachable, then the
        MCP handshake, then the tool list. When something fails you learn which
        layer failed, instead of just "no conecta".
"""

import asyncio
import ipaddress
import socket
import ssl
import sys
from urllib.parse import urlparse

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

DEFAULT_PORT = 8100
TCP_TIMEOUT = 5.0
MCP_TIMEOUT = 15.0

OK = "[ok]"
FAIL = "[--]"


def local_ipv4_addresses() -> list[str]:
    """Every IPv4 address this machine has, loopback and link-local aside."""
    found: set[str] = set()

    # The address used to reach the outside world -- with a VPN up, this is the
    # VPN's, which is exactly why the full list below matters too.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("8.8.8.8", 80))  # UDP connect sends nothing
            found.add(probe.getsockname()[0])
        except OSError:
            pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except socket.gaierror:
        pass

    addresses = []
    for address in found:
        parsed = ipaddress.IPv4Address(address)
        if not (parsed.is_loopback or parsed.is_link_local):
            addresses.append(address)
    return sorted(addresses, key=lambda a: (not ipaddress.IPv4Address(a).is_private, a))


def tcp_reachable(host: str, port: int) -> tuple[bool, str]:
    try:
        resolved = socket.gethostbyname(host)
    except socket.gaierror as exc:
        return False, f"no se pudo resolver '{host}': {exc}"

    # A refused connection and a silently dropped one mean different things, and
    # they are the two failures worth telling apart on a LAN: refused = nothing
    # is listening there; timeout = a firewall is eating the packets (or the IP
    # belongs to nobody).
    try:
        with socket.create_connection((resolved, port), timeout=TCP_TIMEOUT):
            return True, f"{resolved}:{port} acepta conexiones"
    except (TimeoutError, socket.timeout):
        return False, (
            f"{resolved}:{port} no respondio en {TCP_TIMEOUT:.0f}s -- algo esta "
            "descartando los paquetes. Firewall del otro equipo, o esa IP no es de nadie."
        )
    except ConnectionRefusedError:
        return False, (
            f"{resolved}:{port} rechazo la conexion -- el equipo esta ahi pero no hay "
            "nada escuchando en ese puerto. Falta arrancar el servidor, o esta bindeado "
            "a 127.0.0.1 en vez de 0.0.0.0."
        )
    except OSError as exc:
        return False, f"{resolved}:{port} inalcanzable -- {exc.strerror or exc}"


def tls_handshake(host: str, port: int) -> tuple[bool, str]:
    """TLS sits between TCP and HTTP, and it fails for its own reasons -- most
    commonly, for a freshly created workers.dev subdomain, a certificate that
    has not been issued yet."""
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=TCP_TIMEOUT) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert()
                names = [v for k, v in cert.get("subjectAltName", ()) if k == "DNS"]
                covers = ", ".join(names[:3]) or "(sin SAN)"
                return True, f"{tls.version()}, certificado para {covers}"
    except ssl.SSLCertVerificationError as exc:
        return False, f"certificado no valido para este host -- {exc.verify_message or exc}"
    except ssl.SSLError as exc:
        return False, (
            f"handshake TLS rechazado ({exc.reason or exc}). En un subdominio "
            "*.workers.dev recien creado esto normalmente significa que Cloudflare "
            "todavia no emite el certificado: esperá unos minutos y reintentá."
        )
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _leaf_errors(exc: BaseException) -> list[str]:
    """Flatten an ExceptionGroup down to the errors that actually happened.

    The MCP client runs its transport in a task group, so a plain failure
    surfaces as 'ExceptionGroup: unhandled errors in a TaskGroup', which says
    nothing about what went wrong. The whole point of this script is to name the
    layer that failed, so unwrap it.
    """
    if isinstance(exc, BaseExceptionGroup):
        found: list[str] = []
        for sub in exc.exceptions:
            found.extend(_leaf_errors(sub))
        return found or [f"{type(exc).__name__}: {exc}"]
    return [f"{type(exc).__name__}: {exc}"]


async def mcp_handshake(url: str) -> tuple[bool, str]:
    try:
        async with asyncio.timeout(MCP_TIMEOUT):
            async with streamable_http_client(url) as (read, write):
                async with ClientSession(read, write) as session:
                    result = await session.initialize()
                    listed = await session.list_tools()
                    names = ", ".join(tool.name for tool in listed.tools) or "(ninguna)"
                    return True, f"{result.server_info.name} -- {len(listed.tools)} tools: {names}"
    except TimeoutError:
        return False, f"el servidor acepto la conexion pero no completo el handshake MCP en {MCP_TIMEOUT}s"
    except Exception as exc:  # noqa: BLE001 -- this is a diagnostic, report anything
        return False, " | ".join(_leaf_errors(exc))


async def check(url: str) -> bool:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        print(f"{FAIL} {url}\n     no parece una URL (falta http:// o el host)")
        return False

    print(f"\n=== {url}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    reachable, detail = tcp_reachable(parsed.hostname, port)
    print(f"{OK if reachable else FAIL} TCP    {detail}")
    if not reachable:
        return False

    if parsed.scheme == "https":
        secure, detail = tls_handshake(parsed.hostname, port)
        print(f"{OK if secure else FAIL} TLS    {detail}")
        if not secure:
            return False

    handshake, detail = await mcp_handshake(url)
    print(f"{OK if handshake else FAIL} MCP    {detail}")
    return handshake


def show_my_urls() -> None:
    addresses = local_ipv4_addresses()
    listening = tcp_reachable("127.0.0.1", DEFAULT_PORT)[0]

    print("Tu servidor flora-mcp en el puerto", DEFAULT_PORT)
    if listening:
        print(f"{OK} esta escuchando en este momento")
    else:
        print(f"{FAIL} no esta escuchando. Arrancalo con:")
        print(f"     flora-mcp --http --host 0.0.0.0 --port {DEFAULT_PORT}")

    print("\nURLs que pueden usar tus companeros (proba cada una hasta que una funcione):")
    for address in addresses:
        private = ipaddress.IPv4Address(address).is_private
        note = "" if private else "   <- publica, probablemente no es la de la LAN"
        print(f"     FLORA_REMOTE_MCP=anthony=http://{address}:{DEFAULT_PORT}/mcp{note}")

    print(
        "\nSi tenes una VPN activa (NordVPN, etc.) apagala para la demo: "
        "\nsuele bloquear el trafico entre equipos de la misma LAN."
    )


async def main() -> int:
    urls = sys.argv[1:]
    if not urls:
        show_my_urls()
        return 0

    results = [await check(url) for url in urls]
    ok = sum(results)
    print(f"\n{ok}/{len(results)} servidores respondieron.")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

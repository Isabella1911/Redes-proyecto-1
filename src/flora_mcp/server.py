"""MCP server entry point: registers the flora tools and serves them.

Two transports, same tools:

- **stdio** (default) -- the host launches this as a subprocess. Nothing here
  writes to stdout, because that channel carries JSON-RPC and a stray print()
  would corrupt the protocol.
- **Streamable HTTP** (``--http``) -- the server listens on a port so a host on
  another machine can reach it. This is what makes the server usable as a
  *remote* MCP server rather than only a local one.

Errors travel back to the host as tool results either way.
"""

import argparse
from typing import Any

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from . import gbif
from .knowledge_base import get_management_info, known_species
from .plantnet import PlantNetError, identify_plant

# The host launches this server as a subprocess with a restricted environment,
# so it loads its own .env for PLANTNET_API_KEY rather than inheriting one.
load_dotenv()

mcp = MCPServer("flora-mcp")


@mcp.tool()
def identify_plant_from_photo(image_path: str, organ: str = "auto") -> dict[str, Any]:
    """Identify a plant species from a local photo using Pl@ntNet.

    image_path may be absolute or a file name inside the workspace folder.
    organ describes what the photo shows: auto, leaf, flower, fruit, bark,
    habit or other. Returns the top candidates with a confidence score each --
    always report the confidence, and treat anything below ~30% as a guess.
    """
    try:
        return identify_plant(image_path, organ=organ)
    except PlantNetError as exc:
        return {"error": str(exc)}


@mcp.tool()
def classify_species_in_country(scientific_name: str, place: str) -> dict[str, Any]:
    """Determine whether a plant species is native, introduced or invasive in a
    country, using GBIF distribution records, the country's GRIIS register of
    introduced species, and the Global Invasive Species Database.

    place accepts a country name or an ISO code ("Guatemala", "GT", "GTM").
    The reply carries a `status`, the `basis` for it and the raw `evidence`.
    GBIF's coverage is uneven, so a status of "presente, estatus no documentado"
    means the species is recorded there but no checklist states its origin --
    report that honestly instead of assuming it is native.
    """
    return gbif.classify_species(scientific_name, place)


@mcp.tool()
def get_management_recommendations(scientific_name: str) -> dict[str, Any]:
    """Control and management measures for a known invasive species, from a
    curated table focused on Mesoamerica.

    Only covers the species listed in `covered_species` when nothing matches;
    it is not a global database, so say so rather than inventing measures.
    """
    info = get_management_info(scientific_name)
    if info is None:
        return {
            "found": False,
            "message": f"No hay recomendaciones curadas para '{scientific_name}'.",
            "covered_species": known_species(),
        }
    return {"found": True, **info}


@mcp.tool()
def list_country_alien_species(place: str, limit: int = 25) -> dict[str, Any]:
    """List the plant species a country's GRIIS register records as alien
    (non-native) there.

    GRIIS is a register of *introduced* species, only some of which are
    invasive, so present these as introduced rather than as invasive. Use
    classify_species_in_country on any individual species to find out which.
    Not every country publishes a GRIIS checklist.
    """
    country = gbif.resolve_country(place)
    if country is None:
        return {"resolved": False, "reason": f"No se pudo resolver '{place}' a un pais."}

    species = gbif.list_griis_species(country["title"], limit=limit)
    if not species:
        return {
            "resolved": True,
            "country": country["title"],
            "species": [],
            "message": f"GBIF no publica un registro GRIIS de plantas para {country['title']}.",
        }
    return {
        "resolved": True,
        "country": country["title"],
        "country_code": country["iso2"],
        "species": species,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="flora-mcp",
        description="MCP server for plant identification and native/introduced/invasive status.",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="serve over Streamable HTTP instead of stdio, so remote hosts can connect",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help=(
            "interface to bind with --http (default: 127.0.0.1, this machine only). "
            "Use 0.0.0.0 to accept connections from the network -- note the server "
            "has no authentication, so only do that on a network you trust."
        ),
    )
    parser.add_argument("--port", type=int, default=8100, help="port for --http (default: 8100)")
    args = parser.parse_args()

    if args.http:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

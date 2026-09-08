"""End-to-end check that the flora server really speaks MCP: it is launched as
a subprocess over stdio, exactly the way the host launches it, and its tools are
listed and called over JSON-RPC.

Only offline tools are exercised here, so the test does not need network access
or a Pl@ntNet key.
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parents[1]

SERVER = StdioServerParameters(
    command=sys.executable,
    args=["-m", "flora_mcp.server"],
    cwd=str(REPO_ROOT),
)

EXPECTED_TOOLS = {
    "identify_plant_from_photo",
    "classify_species_in_country",
    "get_management_recommendations",
    "list_country_alien_species",
}


async def _list_tools() -> set[str]:
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            return {tool.name for tool in listed.tools}


async def _call(tool_name: str, arguments: dict) -> dict:
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            assert not result.is_error, result.content
            text = "\n".join(b.text for b in result.content if b.type == "text")
            return json.loads(text)


def test_server_advertises_all_its_tools():
    assert asyncio.run(_list_tools()) == EXPECTED_TOOLS


def test_management_tool_returns_curated_advice_over_the_wire():
    payload = asyncio.run(
        _call("get_management_recommendations", {"scientific_name": "Eichhornia crassipes"})
    )
    assert payload["found"] is True
    assert payload["urgency"] == "alta"
    assert payload["methods"]


def test_unknown_species_reports_its_coverage_instead_of_inventing_advice():
    payload = asyncio.run(
        _call("get_management_recommendations", {"scientific_name": "Quercus robur"})
    )
    assert payload["found"] is False
    assert "covered_species" in payload


def test_missing_photo_comes_back_as_an_actionable_error_not_a_crash():
    payload = asyncio.run(
        _call("identify_plant_from_photo", {"image_path": "no-existe-jamas.jpg"})
    )
    assert "error" in payload

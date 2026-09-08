"""Tool names are namespaced per server, and calls route back to the right one.

This matters as soon as two connected servers publish the same tool name --
which happens the moment this project's own server is reached both locally over
stdio and remotely over HTTP, and could happen with any two people's servers.
"""

import asyncio
from types import SimpleNamespace

import pytest

from flora_assistant.mcp_manager import MCPManager, exposed_name


class FakeSession:
    """The slice of ClientSession that MCPManager actually uses."""

    def __init__(self, tool_names: list[str]) -> None:
        self._tool_names = tool_names
        self.calls: list[tuple[str, dict]] = []

    async def initialize(self) -> None:
        return None

    async def list_tools(self):
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name=name,
                    description=f"hace {name}",
                    input_schema={"type": "object", "properties": {}},
                )
                for name in self._tool_names
            ]
        )

    async def call_tool(self, name: str, arguments: dict):
        self.calls.append((name, arguments))
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=f"resultado de {name}")],
            is_error=False,
        )


async def _manager_with(**servers: list[str]) -> tuple[MCPManager, dict[str, FakeSession]]:
    manager = MCPManager()
    sessions = {name: FakeSession(tools) for name, tools in servers.items()}
    for name, session in sessions.items():
        await manager._register_session(name, session)
    return manager, sessions


def test_exposed_name_is_valid_for_the_anthropic_api():
    import re

    name = exposed_name("flora-remoto", "classify_species_in_country")
    assert name == "flora-remoto__classify_species_in_country"
    assert re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", name)


def test_two_servers_with_the_same_tool_name_both_survive():
    async def scenario():
        manager, _ = await _manager_with(
            flora=["classify_species_in_country"],
            remoto=["classify_species_in_country"],
        )
        return await manager.list_all_tools()

    tools = asyncio.run(scenario())
    names = [tool["name"] for tool in tools]

    assert names == [
        "flora__classify_species_in_country",
        "remoto__classify_species_in_country",
    ]
    # The duplicate names that would have been sent to Claude before are gone.
    assert len(set(names)) == len(names)


def test_a_call_reaches_the_right_server_under_its_own_tool_name():
    async def scenario():
        manager, sessions = await _manager_with(
            flora=["classify_species_in_country"],
            remoto=["classify_species_in_country"],
        )
        text = await manager.call_tool(
            "remoto__classify_species_in_country", {"place": "Guatemala"}
        )
        return text, sessions

    text, sessions = asyncio.run(scenario())

    assert text == "resultado de classify_species_in_country"
    # The remote server was called; the local one was left alone. And the tool
    # name sent over the wire is the server's own, not the namespaced one.
    assert sessions["remoto"].calls == [
        ("classify_species_in_country", {"place": "Guatemala"})
    ]
    assert sessions["flora"].calls == []


def test_the_sidebar_listing_keeps_the_plain_tool_names():
    async def scenario():
        manager, _ = await _manager_with(flora=["identify_plant_from_photo"], git=["git_log"])
        return await manager.list_tools_by_server()

    servers = asyncio.run(scenario())

    assert servers == [
        {
            "name": "flora",
            "tools": [
                {"name": "identify_plant_from_photo", "description": "hace identify_plant_from_photo"}
            ],
        },
        {"name": "git", "tools": [{"name": "git_log", "description": "hace git_log"}]},
    ]


def test_a_failed_server_is_listed_as_down_rather_than_omitted():
    async def scenario():
        manager, _ = await _manager_with(flora=["identify_plant_from_photo"])
        manager.startup_errors["library"] = "ConnectionError: MySQL no responde"
        return await manager.list_tools_by_server()

    servers = asyncio.run(scenario())
    down = [s for s in servers if s.get("error")]

    assert len(down) == 1
    assert down[0]["name"] == "library"
    assert down[0]["tools"] == []


def test_calling_an_unknown_tool_fails_loudly():
    async def scenario():
        manager, _ = await _manager_with(flora=["identify_plant_from_photo"])
        return await manager.call_tool("no__existe", {})

    with pytest.raises(KeyError):
        asyncio.run(scenario())

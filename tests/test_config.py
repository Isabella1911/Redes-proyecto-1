import pytest

from flora_assistant.config import remote_servers_from_env


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("FLORA_REMOTE_MCP", raising=False)


def test_no_remote_servers_by_default():
    assert remote_servers_from_env() == []


def test_a_bare_url_gets_a_generated_name(monkeypatch):
    monkeypatch.setenv("FLORA_REMOTE_MCP", "https://flora.example.com/mcp")
    (server,) = remote_servers_from_env()
    assert server.name == "remoto1"
    assert server.url == "https://flora.example.com/mcp"


def test_a_named_entry_keeps_its_name(monkeypatch):
    monkeypatch.setenv("FLORA_REMOTE_MCP", "flora-remoto=http://10.0.0.5:8100/mcp")
    (server,) = remote_servers_from_env()
    assert server.name == "flora-remoto"
    assert server.url == "http://10.0.0.5:8100/mcp"


def test_several_entries_and_stray_whitespace(monkeypatch):
    monkeypatch.setenv(
        "FLORA_REMOTE_MCP", " compa=https://x/mcp , https://y/mcp ,, "
    )
    servers = remote_servers_from_env()
    assert [(s.name, s.url) for s in servers] == [
        ("compa", "https://x/mcp"),
        ("remoto2", "https://y/mcp"),
    ]


def test_a_query_string_is_not_mistaken_for_a_name(monkeypatch):
    monkeypatch.setenv("FLORA_REMOTE_MCP", "https://x/mcp?token=abc")
    (server,) = remote_servers_from_env()
    assert server.url == "https://x/mcp?token=abc"

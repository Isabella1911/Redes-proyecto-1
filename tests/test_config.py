import pytest

from flora_assistant.config import http_servers, remote_servers_from_env, stdio_servers


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


# --- the configuration must be read late, not at import time -----------------
# This module is imported before main.py/web.py call load_dotenv(), so anything
# resolved at import time silently misses the .env. That bug shipped once: the
# remote server declared in .env never connected, and nothing failed loudly.


def test_remote_servers_are_read_when_asked_not_at_import(monkeypatch):
    # flora_assistant.config was imported long before this line ran. If the
    # value were captured at import time, this would come back empty.
    monkeypatch.setenv("FLORA_REMOTE_MCP", "tardio=https://tarde.example.com/mcp")
    urls = [server.url for server in http_servers()]
    assert urls == ["https://tarde.example.com/mcp"]


def test_the_plant_server_gets_its_key_from_the_environment_at_connect_time(monkeypatch):
    monkeypatch.setenv("PLANTNET_API_KEY", "clave-cargada-tarde")
    (flora,) = [s for s in stdio_servers() if s.name == "flora"]
    assert flora.env["PLANTNET_API_KEY"] == "clave-cargada-tarde"


def test_the_plant_server_is_pointed_back_at_this_repos_workspace():
    # It runs with its own repository as the working directory now, so a
    # relative image name would otherwise resolve against *its* folder.
    (flora,) = [s for s in stdio_servers() if s.name == "flora"]
    images = flora.env["FLORA_IMAGES_DIR"]
    assert images.endswith("workspace")
    assert "Redes-proyecto-1" in images


def test_the_plant_server_is_not_handed_the_anthropic_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "no-deberia-viajar")
    (flora,) = [s for s in stdio_servers() if s.name == "flora"]
    assert "ANTHROPIC_API_KEY" not in flora.env

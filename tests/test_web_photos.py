"""The photo endpoints the web UI adds: listing, serving and uploading.

These exercise the routes directly against a temporary workspace, so no MCP
server is started and no API key is needed -- the chat routes are the only part
of the app that talks to Claude.
"""

import importlib

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

JPEG = b"\xff\xd8\xff" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A test app wired to a throwaway workspace.

    `WORKSPACE` is read at import time, so the module is reloaded with the env
    var set rather than patched afterwards -- that way the module-level constant
    and the routes agree.
    """
    monkeypatch.setenv("FLORA_IMAGES_DIR", str(tmp_path))
    web = importlib.reload(importlib.import_module("flora_assistant.web"))

    # Only the photo routes: mounting the full app would start every MCP server
    # through its lifespan.
    app = Starlette(
        routes=[
            Route("/api/photos", web.api_photos),
            Route("/api/photos/{name}", web.api_photo_file),
            Route("/api/upload", web.api_upload, methods=["POST"]),
        ]
    )
    yield TestClient(app), tmp_path

    # Leave the module bound to the real workspace for any later test.
    monkeypatch.delenv("FLORA_IMAGES_DIR", raising=False)
    importlib.reload(web)


def test_listing_an_empty_workspace(client):
    api, _ = client
    assert api.get("/api/photos").json() == {"photos": []}


def test_listing_ignores_non_images(client):
    api, workspace = client
    (workspace / "planta.jpg").write_bytes(JPEG)
    (workspace / "notas.txt").write_text("no soy una foto")

    photos = api.get("/api/photos").json()["photos"]
    assert [p["name"] for p in photos] == ["planta.jpg"]
    assert photos[0]["url"] == "/api/photos/planta.jpg"


def test_upload_stores_the_file_and_reports_it(client):
    api, workspace = client
    response = api.post("/api/upload", files={"file": ("mi foto.jpg", JPEG, "image/jpeg")})

    assert response.status_code == 201
    # The space is sanitised out of the stored name.
    assert response.json()["name"] == "mi_foto.jpg"
    assert (workspace / "mi_foto.jpg").read_bytes() == JPEG


def test_upload_never_overwrites_an_existing_photo(client):
    api, workspace = client
    (workspace / "planta.jpg").write_bytes(JPEG)

    name = api.post("/api/upload", files={"file": ("planta.jpg", JPEG, "image/jpeg")}).json()["name"]

    assert name == "planta-1.jpg"
    assert (workspace / "planta.jpg").read_bytes() == JPEG


def test_upload_files_by_real_format_not_by_the_name_it_arrived_with(client):
    # Renaming a PNG to .jpg is an easy mistake; storing it as .jpg would make
    # plantnet.py guess the wrong mime type from the name later.
    api, workspace = client
    name = api.post("/api/upload", files={"file": ("planta.jpg", PNG, "image/jpeg")}).json()["name"]

    assert name == "planta.png"
    assert (workspace / "planta.png").read_bytes() == PNG


def test_upload_rejects_an_unsupported_extension(client):
    api, _ = client
    response = api.post("/api/upload", files={"file": ("script.svg", b"<svg/>", "image/svg+xml")})
    assert response.status_code == 415


def test_upload_rejects_a_file_that_is_not_really_an_image(client):
    api, workspace = client
    response = api.post("/api/upload", files={"file": ("falsa.jpg", b"soy texto", "image/jpeg")})

    assert response.status_code == 415
    assert list(workspace.iterdir()) == []


def test_upload_rejects_an_oversized_image(client, monkeypatch):
    api, workspace = client
    import flora_assistant.web as web

    monkeypatch.setattr(web, "MAX_UPLOAD_BYTES", 128)
    response = api.post("/api/upload", files={"file": ("grande.jpg", JPEG + b"\x00" * 512, "image/jpeg")})

    assert response.status_code == 413
    assert list(workspace.iterdir()) == []


def test_serving_a_photo_returns_its_bytes(client):
    api, workspace = client
    (workspace / "planta.jpg").write_bytes(JPEG)
    assert api.get("/api/photos/planta.jpg").content == JPEG


@pytest.mark.parametrize(
    "attempt",
    ["../.env", "..%2F.env", "subdir/../../secret.jpg"],
)
def test_serving_refuses_to_escape_the_workspace(client, attempt):
    api, workspace = client
    (workspace.parent / ".env").write_text("ANTHROPIC_API_KEY=secreto")

    response = api.get(f"/api/photos/{attempt}")

    assert response.status_code == 404
    assert b"secreto" not in response.content

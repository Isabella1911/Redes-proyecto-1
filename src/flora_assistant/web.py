"""Web UI: a lightweight Starlette app serving a browser chat interface for the
same Chatbot/MCPManager the console REPL (main.py) uses.

It also owns the photo workflow the console cannot offer: uploading images into
the workspace folder and browsing what is already there. The workspace is the
one directory both the Filesystem MCP server and `flora-mcp` can see, so a photo
dropped here is immediately identifiable by name.
"""

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import find_dotenv, load_dotenv
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .chatbot import Chatbot
from .mcp_manager import MCPManager

STATIC_DIR = Path(__file__).parent / "static"

# Same default as flora_mcp.plantnet, and the same env var overrides both, so
# the folder the UI writes to is always the folder the server reads from.
WORKSPACE = Path(os.environ.get("FLORA_IMAGES_DIR", "workspace")).resolve()

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

def detect_suffix(data: bytes) -> str | None:
    """The real format of an image from its leading bytes, or None if it is not
    one Pl@ntNet accepts.

    The stored file gets this extension rather than the uploaded name's, so a
    PNG someone renamed to .jpg is filed correctly instead of confusing the
    mime-type guess in flora_mcp.plantnet later.
    """
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    return None

state: dict[str, MCPManager | Chatbot | None] = {"manager": None, "chatbot": None}


@asynccontextmanager
async def lifespan(app: Starlette):
    load_dotenv(find_dotenv(usecwd=True))
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    manager = MCPManager()
    await manager.connect_all()
    state["manager"] = manager
    state["chatbot"] = Chatbot(manager)
    try:
        yield
    finally:
        await manager.close()


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------


def _resolve_in_workspace(name: str) -> Path | None:
    """Resolve a photo name to a real file inside the workspace, or None.

    `Path(name).name` drops any directory part, and comparing the resolved
    parent to WORKSPACE rejects anything that escapes it (a symlink, say).
    """
    candidate = (WORKSPACE / Path(name).name).resolve()
    if candidate.parent != WORKSPACE or not candidate.is_file():
        return None
    return candidate


def _unique_target(filename: str, suffix: str) -> Path:
    """A free path in the workspace for an uploaded file, keeping its name where
    possible and never overwriting an existing photo."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._")
    stem = Path(stem).stem or "foto"

    target = WORKSPACE / f"{stem}{suffix}"
    counter = 1
    while target.exists():
        target = WORKSPACE / f"{stem}-{counter}{suffix}"
        counter += 1
    return target


def _photo_entries() -> list[dict]:
    photos = [
        path
        for path in WORKSPACE.iterdir()
        if path.is_file() and path.suffix.lower() in ALLOWED_SUFFIXES
    ]
    # Newest first, so a photo just uploaded is the first thing on screen.
    photos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {"name": p.name, "size": p.stat().st_size, "url": f"/api/photos/{p.name}"}
        for p in photos
    ]


async def api_photos(request: Request) -> JSONResponse:
    return JSONResponse({"photos": _photo_entries()})


async def api_photo_file(request: Request) -> FileResponse | JSONResponse:
    path = _resolve_in_workspace(request.path_params["name"])
    if path is None:
        return JSONResponse({"error": "no existe esa foto"}, status_code=404)
    return FileResponse(path)


async def api_upload(request: Request) -> JSONResponse:
    form = await request.form()
    upload = form.get("file")
    if upload is None or not getattr(upload, "filename", ""):
        return JSONResponse({"error": "no se recibio ningun archivo"}, status_code=400)

    suffix = Path(upload.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        return JSONResponse(
            {"error": f"formato no soportado ({suffix or 'sin extension'}). Use JPG, PNG o WebP."},
            status_code=415,
        )

    # Read in chunks so an oversized file is rejected without being held whole
    # in memory first.
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(64 * 1024):
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            return JSONResponse(
                {"error": f"la imagen supera el limite de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB"},
                status_code=413,
            )
        chunks.append(chunk)

    data = b"".join(chunks)
    real_suffix = detect_suffix(data)
    if real_suffix is None:
        return JSONResponse(
            {"error": "el archivo no parece una imagen JPG, PNG o WebP"}, status_code=415
        )

    target = _unique_target(upload.filename, real_suffix)
    target.write_bytes(data)
    return JSONResponse(
        {"name": target.name, "size": size, "url": f"/api/photos/{target.name}"},
        status_code=201,
    )


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


async def index(request: Request) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


async def api_tools(request: Request) -> JSONResponse:
    manager: MCPManager = state["manager"]
    servers = await manager.list_tools_by_server()
    return JSONResponse({"servers": servers})


async def api_chat(request: Request) -> JSONResponse:
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "empty message"}, status_code=400)

    chatbot: Chatbot = state["chatbot"]
    try:
        reply = await chatbot.send(message)
    except Exception as exc:  # noqa: BLE001 -- surface any failure to the UI
        return JSONResponse({"error": str(exc)}, status_code=500)

    return JSONResponse({"reply": reply, "tool_calls": chatbot.last_tool_calls})


app = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/", index),
        Route("/api/tools", api_tools),
        Route("/api/chat", api_chat, methods=["POST"]),
        Route("/api/photos", api_photos),
        Route("/api/photos/{name}", api_photo_file),
        Route("/api/upload", api_upload, methods=["POST"]),
        Mount("/static", StaticFiles(directory=STATIC_DIR), name="static"),
    ],
)


def run() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8765)


if __name__ == "__main__":
    run()

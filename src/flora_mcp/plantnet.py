"""Pl@ntNet client: photo of a plant in, candidate species out.

Needs a free API key from https://my.plantnet.org/ in ``PLANTNET_API_KEY``.
The key is read at call time, not at import time, so a ``.env`` loaded by the
host after this module is imported still takes effect.
"""

import mimetypes
import os
from pathlib import Path
from typing import Any

import requests

PLANTNET_URL = "https://my-api.plantnet.org/v2/identify/all"
TIMEOUT = 60

# Which part of the plant the photo shows. "auto" lets Pl@ntNet decide, which
# is the right default when the user just points at a file.
VALID_ORGANS = {"auto", "leaf", "flower", "fruit", "bark", "habit", "other"}

# Relative image paths are resolved against this directory -- the same folder
# the Filesystem MCP server exposes -- so the model can pass "planta1.jpg"
# without knowing the server's working directory.
IMAGES_DIR = Path(os.environ.get("FLORA_IMAGES_DIR", "workspace")).resolve()


class PlantNetError(RuntimeError):
    """Raised for anything the caller can act on: missing key, missing file,
    or an error response from Pl@ntNet."""


def resolve_image_path(image_path: str) -> Path:
    """Locate an image, accepting an absolute path or a name relative to
    ``IMAGES_DIR``."""
    candidate = Path(image_path).expanduser()
    if candidate.is_absolute():
        if not candidate.is_file():
            raise PlantNetError(f"No existe la imagen: {candidate}")
        return candidate

    # Tolerate the model prefixing the workspace folder it saw in a file
    # listing ("workspace/planta1.jpg") as well as a bare file name.
    for option in (IMAGES_DIR / candidate, IMAGES_DIR / candidate.name, candidate):
        if option.is_file():
            return option.resolve()

    available = sorted(p.name for p in IMAGES_DIR.glob("*") if p.is_file())
    raise PlantNetError(
        f"No existe la imagen '{image_path}' en {IMAGES_DIR}. "
        f"Archivos disponibles: {', '.join(available) if available else '(ninguno)'}"
    )


def identify_plant(image_path: str, organ: str = "auto", max_results: int = 3) -> dict[str, Any]:
    """Send one photo to Pl@ntNet and return its best species candidates."""
    api_key = os.environ.get("PLANTNET_API_KEY")
    if not api_key:
        raise PlantNetError(
            "Falta PLANTNET_API_KEY. Cree una clave gratuita en "
            "https://my.plantnet.org/ y agreguela al archivo .env."
        )

    if organ not in VALID_ORGANS:
        raise PlantNetError(
            f"Organo '{organ}' no valido. Use uno de: {', '.join(sorted(VALID_ORGANS))}."
        )

    path = resolve_image_path(image_path)
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"

    with path.open("rb") as image:
        response = requests.post(
            PLANTNET_URL,
            params={"api-key": api_key, "lang": "es"},
            files={"images": (path.name, image, mime)},
            data={"organs": organ},
            timeout=TIMEOUT,
        )

    if response.status_code == 404:
        # Pl@ntNet answers 404 when it recognised nothing at all, which is a
        # normal outcome rather than a failure.
        return {"found": False, "image": path.name, "candidates": []}
    if response.status_code in (401, 403):
        raise PlantNetError("Pl@ntNet rechazo la API key (401/403). Revise PLANTNET_API_KEY.")
    if response.status_code == 429:
        raise PlantNetError("Se agoto la cuota diaria de Pl@ntNet (429). Intente mas tarde.")
    response.raise_for_status()

    results = response.json().get("results", [])[:max_results]
    if not results:
        return {"found": False, "image": path.name, "candidates": []}

    return {
        "found": True,
        "image": path.name,
        "organ": organ,
        "candidates": [
            {
                "scientific_name": r["species"]["scientificNameWithoutAuthor"],
                "common_names": r["species"].get("commonNames", []),
                "family": r["species"].get("family", {}).get("scientificNameWithoutAuthor"),
                "confidence": round(r["score"] * 100, 1),
            }
            for r in results
        ],
    }

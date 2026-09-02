import os
import base64
import requests

PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY")
PLANTNET_URL = "https://my-api.plantnet.org/v2/identify/all"
GBIF_SPECIES_URL = "https://api.gbif.org/v1/species/match"
GBIF_OCCURRENCE_URL = "https://api.gbif.org/v1/occurrence/search"


def identify_plant_image(image_path: str) -> dict:
    """Envía una imagen a Pl@ntNet y retorna las mejores coincidencias."""
    with open(image_path, "rb") as f:
        files = {"images": (os.path.basename(image_path), f, "image/jpeg")}
        params = {"api-key": PLANTNET_API_KEY}
        response = requests.post(PLANTNET_URL, files=files, params=params, data={"organs": "leaf"})

    response.raise_for_status()
    data = response.json()

    if not data.get("results"):
        return {"found": False}

    best = data["results"][0]
    return {
        "found": True,
        "scientific_name": best["species"]["scientificNameWithoutAuthor"],
        "common_names": best["species"].get("commonNames", []),
        "confidence": round(best["score"] * 100, 1),
    }


def get_gbif_species_key(scientific_name: str) -> int | None:
    """Resuelve el nombre científico a un taxonKey de GBIF."""
    resp = requests.get(GBIF_SPECIES_URL, params={"name": scientific_name})
    resp.raise_for_status()
    data = resp.json()
    return data.get("usageKey")


def check_regional_occurrence(scientific_name: str, country_code: str) -> dict:
    """
    Heurística: si GBIF tiene registros de la especie en el país indicado,
    se considera presente/naturalizada. GBIF no da un booleano directo de
    'invasora', así que esto se combina con la knowledge_base para el veredicto.
    """
    species_key = get_gbif_species_key(scientific_name)
    if species_key is None:
        return {"resolved": False}

    resp = requests.get(GBIF_OCCURRENCE_URL, params={
        "taxonKey": species_key,
        "country": country_code,
        "limit": 1,
    })
    resp.raise_for_status()
    data = resp.json()

    return {
        "resolved": True,
        "records_in_country": data.get("count", 0),
        "taxon_key": species_key,
    }
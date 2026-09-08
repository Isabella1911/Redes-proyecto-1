"""Thin client over the public GBIF API (no API key required).

GBIF is what backs the native / introduced / invasive verdict:

- ``species/{key}/distributions`` carries a per-country ``establishmentMeans``
  (NATIVE, INTRODUCED, NATURALISED, MANAGED, INVASIVE) contributed by national
  checklists.
- Every country has a GRIIS checklist (Global Register of Introduced and
  Invasive Species). Membership means the species is alien in that country.
- The Global Invasive Species Database (GISD) lists species documented as
  invasive somewhere in the world.

Coverage is uneven -- many species have no distribution row at all for a given
country -- so the classifier reports the evidence it actually found and falls
back to raw occurrence counts instead of guessing.
"""

from functools import lru_cache
from typing import Any

import requests

API = "https://api.gbif.org/v1"
TIMEOUT = 30

# Global Invasive Species Database, published on GBIF as a checklist dataset.
GISD_DATASET_KEY = "b351a324-77c4-41c9-a909-f30f77268bc4"

GRIIS_TITLE_PREFIX = "Global Register of Introduced and Invasive Species"

# GBIF's establishmentMeans values mapped onto the three categories this
# project reports. NATURALISED and MANAGED both mean the species did not get
# there on its own, so they roll up into "introducida".
MEANS_TO_CATEGORY = {
    "NATIVE": "nativa",
    "INTRODUCED": "introducida",
    "NATURALISED": "introducida",
    "NATURALIZED": "introducida",
    "MANAGED": "introducida",
    "INVASIVE": "invasora",
}

_session = requests.Session()


def _get(path: str, **params: Any) -> Any:
    response = _session.get(f"{API}/{path}", params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Countries
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _countries() -> tuple[dict[str, str], ...]:
    return tuple(
        {"iso2": c["iso2"], "iso3": c.get("iso3", ""), "title": c["title"]}
        for c in _get("enumeration/country")
    )


def resolve_country(place: str) -> dict[str, str] | None:
    """Turn a place name or ISO code ("Guatemala", "GT", "GTM") into a GBIF
    country entry, or None when nothing matches."""
    needle = place.strip().casefold()
    if not needle:
        return None

    countries = _countries()
    for country in countries:
        if needle in (country["iso2"].casefold(), country["iso3"].casefold()):
            return dict(country)
    for country in countries:
        if country["title"].casefold() == needle:
            return dict(country)
    # Last resort, so a partial name like "Guatem" still resolves.
    for country in countries:
        if country["title"].casefold().startswith(needle):
            return dict(country)
    return None


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------


@lru_cache(maxsize=256)
def match_species(scientific_name: str) -> dict[str, Any]:
    """Resolve a scientific name against the GBIF backbone taxonomy.

    Returns both ``usage_key`` (the name as given) and ``accepted_key``: a
    synonym and its accepted name are different keys, and each checklist is
    indexed under whichever one its compiler used, so every lookup downstream
    has to try both. Eichhornia crassipes vs Pontederia crassipes is the
    canonical example -- GISD lists the synonym, GBIF's backbone the accepted
    name.
    """
    data = _get("species/match", name=scientific_name)
    usage_key = data.get("usageKey")
    if usage_key is None:
        return {"resolved": False, "input_name": scientific_name}

    return {
        "resolved": True,
        "input_name": scientific_name,
        "usage_key": usage_key,
        "accepted_key": data.get("acceptedUsageKey") or usage_key,
        "scientific_name": data.get("scientificName"),
        "canonical_name": data.get("canonicalName"),
        "rank": data.get("rank"),
        "taxonomic_status": data.get("status"),
        "match_type": data.get("matchType"),
        "confidence": data.get("confidence"),
        "family": data.get("family"),
        "kingdom": data.get("kingdom"),
    }


def _taxon_keys(match: dict[str, Any]) -> list[int]:
    keys = [match["usage_key"]]
    if match["accepted_key"] not in keys:
        keys.append(match["accepted_key"])
    return keys


# ---------------------------------------------------------------------------
# Distributions and checklist membership
# ---------------------------------------------------------------------------


@lru_cache(maxsize=256)
def _distributions(taxon_key: int) -> tuple[dict[str, Any], ...]:
    data = _get(f"species/{taxon_key}/distributions", limit=1000)
    return tuple(data.get("results", []))


def distributions_in_country(match: dict[str, Any], iso2: str) -> list[dict[str, Any]]:
    """Every distribution row published for this taxon in one country."""
    rows: list[dict[str, Any]] = []
    for key in _taxon_keys(match):
        for row in _distributions(key):
            if row.get("country") != iso2:
                continue
            rows.append(
                {
                    "establishment_means": row.get("establishmentMeans"),
                    "occurrence_status": row.get("status"),
                    "source": row.get("source") or "",
                }
            )
    return rows


def native_range(match: dict[str, Any], limit: int = 25) -> list[str]:
    """ISO codes of the countries where GBIF records the species as native."""
    countries: list[str] = []
    for key in _taxon_keys(match):
        for row in _distributions(key):
            country = row.get("country")
            if row.get("establishmentMeans") == "NATIVE" and country not in (None, *countries):
                countries.append(country)
    return countries[:limit]


@lru_cache(maxsize=256)
def _related_dataset_keys(taxon_key: int) -> frozenset[str]:
    """Datasets holding a name usage that maps to this backbone taxon."""
    data = _get(f"species/{taxon_key}/related", limit=1000)
    return frozenset(
        row["datasetKey"] for row in data.get("results", []) if row.get("datasetKey")
    )


def _dataset_keys(match: dict[str, Any]) -> frozenset[str]:
    keys: frozenset[str] = frozenset()
    for key in _taxon_keys(match):
        keys |= _related_dataset_keys(key)
    return keys


@lru_cache(maxsize=64)
def griis_dataset_key(country_title: str) -> str | None:
    """Find a country's GRIIS checklist on GBIF.

    Titles are not punctuated consistently across countries ("- Cuba",
    "-Samoa", "- Guatemala"), so compare the country name that follows the
    common prefix rather than the whole title.
    """
    data = _get(
        "dataset/search",
        q=f"{GRIIS_TITLE_PREFIX} {country_title}",
        type="CHECKLIST",
        limit=20,
    )
    wanted = country_title.casefold()
    for dataset in data.get("results", []):
        title = dataset.get("title", "")
        if GRIIS_TITLE_PREFIX not in title:
            continue
        tail = title.split(GRIIS_TITLE_PREFIX, 1)[1].strip(" -").casefold()
        if tail == wanted:
            return dataset["key"]
    return None


def in_gisd(match: dict[str, Any]) -> bool:
    """Is the species in the Global Invasive Species Database?"""
    return GISD_DATASET_KEY in _dataset_keys(match)


def in_country_griis(match: dict[str, Any], country_title: str) -> bool | None:
    """True/False when the country publishes a GRIIS checklist, None when it
    does not -- which is not the same as the species being absent from it."""
    dataset_key = griis_dataset_key(country_title)
    if dataset_key is None:
        return None
    return dataset_key in _dataset_keys(match)


def list_griis_species(
    country_title: str, kingdom: str = "Plantae", limit: int = 25
) -> list[dict[str, Any]]:
    """The alien species a country's GRIIS checklist records, one kingdom at a
    time (the register covers animals and fungi too)."""
    dataset_key = griis_dataset_key(country_title)
    if dataset_key is None:
        return []

    # A GRIIS register lists animals and fungi alongside plants, and GBIF's
    # species/search cannot filter by kingdom inside a checklist dataset (its
    # taxon keys are dataset-local, not backbone keys), so page through and
    # filter client-side until enough plants are collected.
    species: list[dict[str, Any]] = []
    page_size = 200
    for offset in range(0, 1000, page_size):
        data = _get(
            "species/search",
            datasetKey=dataset_key,
            rank="SPECIES",
            limit=page_size,
            offset=offset,
        )
        results = data.get("results", [])
        for row in results:
            if kingdom and row.get("kingdom") != kingdom:
                continue
            species.append(
                {
                    "scientific_name": row.get("scientificName"),
                    "canonical_name": row.get("canonicalName"),
                    "family": row.get("family"),
                }
            )
            if len(species) >= limit:
                return species
        if data.get("endOfRecords") or not results:
            break
    return species


def occurrence_count(match: dict[str, Any], iso2: str) -> int:
    """How many observation records GBIF holds for the species in a country."""
    total = 0
    for key in _taxon_keys(match):
        data = _get("occurrence/search", taxonKey=key, country=iso2, limit=0)
        total += data.get("count", 0)
    return total


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


def classify_species(scientific_name: str, place: str) -> dict[str, Any]:
    """Decide whether a species is native, introduced or invasive in a place.

    GBIF publishes no single authoritative field for this, so the verdict is a
    documented heuristic and the evidence behind it travels with it:

    1. A distribution row for that country wins -- it is a national checklist
       stating establishmentMeans directly.
    2. Otherwise, presence in the country's GRIIS register means the species is
       alien there; combined with a GISD listing it is reported as invasive.
    3. Otherwise, occurrence records only prove the species has been observed
       there, reported as "presente, estatus no documentado".
    """
    country = resolve_country(place)
    if country is None:
        return {
            "resolved": False,
            "reason": (
                f"No se pudo resolver '{place}' a un pais. Use el nombre del pais "
                "o su codigo ISO (por ejemplo 'Guatemala' o 'GT')."
            ),
        }

    match = match_species(scientific_name)
    if not match["resolved"]:
        return {
            "resolved": False,
            "country": country["title"],
            "reason": f"GBIF no reconoce el nombre cientifico '{scientific_name}'.",
        }

    iso2 = country["iso2"]
    rows = distributions_in_country(match, iso2)
    means = [row["establishment_means"] for row in rows if row["establishment_means"]]
    gisd = in_gisd(match)
    griis = in_country_griis(match, country["title"])
    occurrences = occurrence_count(match, iso2)

    if "INVASIVE" in means:
        status = "invasora"
        basis = "checklist nacional (establishmentMeans=INVASIVE)"
    elif means:
        # A country can carry rows from several checklists. Prefer a non-native
        # signal over a lone NATIVE row, so a naturalised alien with one stale
        # native record is not reported as native.
        introduced = next(
            (m for m in means if MEANS_TO_CATEGORY.get(m) == "introducida"), None
        )
        if introduced and gisd:
            status = "invasora"
            basis = f"introducida segun checklist nacional ({introduced}) y listada en GISD"
        elif introduced:
            status = "introducida"
            basis = f"checklist nacional (establishmentMeans={introduced})"
        else:
            status = MEANS_TO_CATEGORY.get(means[0], "desconocida")
            basis = f"checklist nacional (establishmentMeans={means[0]})"
    elif griis:
        status = "invasora" if gisd else "introducida"
        basis = "registrada en el GRIIS del pais" + (" y en GISD" if gisd else "")
    elif occurrences > 0:
        status = "presente, estatus no documentado"
        basis = (
            f"{occurrences} registros de ocurrencia en GBIF, pero ningun checklist "
            "publica su estatus para este pais"
        )
    else:
        status = "sin registros"
        basis = "GBIF no tiene registros de esta especie en el pais"

    return {
        "resolved": True,
        "species": match["scientific_name"],
        "canonical_name": match["canonical_name"],
        "taxonomic_status": match["taxonomic_status"],
        "family": match["family"],
        "country": country["title"],
        "country_code": iso2,
        "status": status,
        "basis": basis,
        "evidence": {
            "distribution_rows": rows,
            "in_country_griis": griis,
            "in_gisd": gisd,
            "occurrence_records": occurrences,
            "native_range_sample": native_range(match),
        },
    }

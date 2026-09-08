"""Curated management advice for invasive species relevant to Mesoamerica.

GBIF says *what* a species is; it does not say what to do about it. This is the
local, hand-written half of the server: a small table of control measures keyed
by scientific name, with synonyms mapped onto the entry they belong to (GBIF and
Pl@ntNet do not always agree on which name is current -- Pl@ntNet still returns
"Eichhornia crassipes" where GBIF's backbone has moved to "Pontederia crassipes").

Sources: CABI Invasive Species Compendium, IUCN GISD species factsheets, and
CONAP/MARN guidance for Guatemala. Extend it as you research your own region.
"""

from typing import Any

MANAGEMENT_DB: dict[str, dict[str, Any]] = {
    "pontederia crassipes": {
        "common_name": "Jacinto de agua / lirio acuatico",
        "urgency": "alta",
        "why": (
            "Forma tapetes flotantes que agotan el oxigeno del agua, bloquean la "
            "navegacion y la pesca, y disparan la evaporacion del cuerpo de agua."
        ),
        "methods": [
            "Control mecanico: extraccion manual o con cosechadora antes de la floracion, retirando la biomasa de la orilla para que no se reintegre al agua.",
            "Control biologico: gorgojos Neochetina bruchi y N. eichhorniae, ya usados en Centroamerica.",
            "Evitar herbicidas cerca de tomas de agua potable o de zonas de pesca.",
            "Reducir la carga de nutrientes (aguas residuales, escorrentia agricola) que alimenta el crecimiento.",
        ],
    },
    "hydrilla verticillata": {
        "common_name": "Hydrilla",
        "urgency": "alta",
        "why": (
            "Se propaga por fragmentos y tuberculos; un solo fragmento en una "
            "lancha o red basta para colonizar otro lago."
        ),
        "methods": [
            "Lavar y secar embarcaciones, remos y redes al salir de un cuerpo de agua infestado.",
            "Cosecha mecanica repetida, sabiendo que los tuberculos sobreviven varios anios en el sedimento.",
            "Control biologico con carpa herbivora esteril solo bajo autorizacion de la autoridad ambiental.",
        ],
    },
    "casuarina equisetifolia": {
        "common_name": "Casuarina / pino australiano",
        "urgency": "media",
        "why": (
            "Desplaza vegetacion costera nativa, acidifica el suelo con su "
            "hojarasca e impide la anidacion de tortugas marinas en playas."
        ),
        "methods": [
            "Cortar y extraer plantulas jovenes antes de que fructifiquen.",
            "Aplicar herbicida al tocon inmediatamente despues del corte (el rebrote es vigoroso).",
            "Restaurar con especies costeras nativas para evitar la recolonizacion.",
        ],
    },
    "leucaena leucocephala": {
        "common_name": "Leucaena / yaje",
        "urgency": "media",
        "why": (
            "Introducida como forraje y lenia, forma matorrales monoespecificos "
            "densos en terrenos perturbados."
        ),
        "methods": [
            "Corte repetido antes de la fructificacion para agotar la reserva de la raiz.",
            "Extraccion de plantulas del banco de semillas tras cada lluvia fuerte.",
            "No sembrarla como cerca viva ni como forraje en areas cercanas a bosque nativo.",
        ],
    },
    "arundo donax": {
        "common_name": "Cania brava / carrizo gigante",
        "urgency": "alta",
        "why": (
            "Coloniza riberas, aumenta el riesgo de incendio y desvia cauces al "
            "atrapar sedimento."
        ),
        "methods": [
            "Extraccion completa de rizomas: el corte solo estimula el rebrote.",
            "Herbicida foliar al final de la temporada de crecimiento, lejos del agua.",
            "Revegetar la ribera con especies nativas de raiz profunda.",
        ],
    },
    "lantana camara": {
        "common_name": "Lantana / cinco negritos",
        "urgency": "media",
        "why": (
            "Ornamental escapada de cultivo, toxica para el ganado y capaz de "
            "impedir la regeneracion del bosque."
        ),
        "methods": [
            "Arranque manual con raiz en suelo humedo, antes de la fructificacion.",
            "Evitar su venta como ornamental cerca de areas protegidas.",
            "Monitorear los bordes de camino, que son su principal via de dispersion.",
        ],
    },
    "salvinia molesta": {
        "common_name": "Helecho de agua gigante",
        "urgency": "alta",
        "why": "Duplica su biomasa en pocos dias y cubre por completo la superficie del agua.",
        "methods": [
            "Control biologico con el gorgojo Cyrtobagous salviniae, el metodo mas efectivo documentado.",
            "Barreras flotantes para concentrar la mata antes de retirarla.",
            "Prohibir su uso en acuarios y estanques ornamentales.",
        ],
    },
}

# Names that should resolve to an entry above but are not its key.
SYNONYMS = {
    "eichhornia crassipes": "pontederia crassipes",
    "eichhornia speciosa": "pontederia crassipes",
    "salvinia auriculata": "salvinia molesta",
}


def _normalise(species_name: str) -> str:
    key = " ".join(species_name.strip().lower().split())
    return SYNONYMS.get(key, key)


def get_management_info(species_name: str) -> dict[str, Any] | None:
    """Control measures for a species, or None if it is not in the table."""
    entry = MANAGEMENT_DB.get(_normalise(species_name))
    if entry is None:
        return None
    return {"scientific_name": _normalise(species_name), **entry}


def known_species() -> list[str]:
    """Every species the table covers, for the model to know its own limits."""
    return sorted(MANAGEMENT_DB)

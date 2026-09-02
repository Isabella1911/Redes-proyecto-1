# Base de conocimiento curada: acciones de manejo por especie invasora conocida.
# Clave: nombre científico en minúsculas.
MANAGEMENT_DB = {
    "eichhornia crassipes": {
        "common_name": "Jacinto de agua",
        "urgency": "alta",
        "methods": [
            "Control mecánico: remoción manual o con maquinaria antes de floración",
            "Control biológico: introducción controlada de Neochetina spp. (gorgojos)",
            "Evitar el uso de herbicidas cerca de fuentes de agua potable",
        ],
    },
    "casuarina equisetifolia": {
        "common_name": "Casuarina / pino australiano",
        "urgency": "media",
        "methods": [
            "Corte y remoción de plántulas jóvenes antes de que fructifiquen",
            "Aplicación de herbicida en el tocón inmediatamente después del corte",
        ],
    },
    # Agrega más especies según lo que investigues para tu región
}

def get_management_info(species_name: str) -> dict | None:
    return MANAGEMENT_DB.get(species_name.strip().lower())
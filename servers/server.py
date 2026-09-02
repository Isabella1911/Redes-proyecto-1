import asyncio
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import json

from clients import identify_plant_image, check_regional_occurrence
from knowledge_base import get_management_info

load_dotenv()

app = Server("plant-identifier")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="identify_plant",
            description="Identifica una especie de planta a partir de una imagen local usando Pl@ntNet.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Ruta local a la imagen de la planta"},
                },
                "required": ["image_path"],
            },
        ),
        Tool(
            name="check_invasive_status",
            description="Determina si una especie (por nombre científico) es nativa, introducida o invasora en un país, cruzando registros de GBIF con una base de manejo curada.",
            inputSchema={
                "type": "object",
                "properties": {
                    "scientific_name": {"type": "string"},
                    "country_code": {"type": "string", "description": "Código ISO de 2 letras, ej. GT"},
                },
                "required": ["scientific_name", "country_code"],
            },
        ),
        Tool(
            name="get_management_recommendations",
            description="Devuelve recomendaciones de manejo/control para una especie invasora conocida.",
            inputSchema={
                "type": "object",
                "properties": {
                    "scientific_name": {"type": "string"},
                },
                "required": ["scientific_name"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "identify_plant":
        result = identify_plant_image(arguments["image_path"])

    elif name == "check_invasive_status":
        species = arguments["scientific_name"]
        country = arguments["country_code"]

        occurrence = check_regional_occurrence(species, country)
        management = get_management_info(species)

        if management:
            status = "invasora (registrada en base de manejo)"
        elif occurrence.get("resolved") and occurrence.get("records_in_country", 0) > 0:
            status = "presente en la región (revisar si es nativa o introducida)"
        else:
            status = "sin registros suficientes para determinar estatus"

        result = {
            "species": species,
            "country": country,
            "status": status,
            "gbif_data": occurrence,
            "has_management_info": management is not None,
        }

    elif name == "get_management_recommendations":
        info = get_management_info(arguments["scientific_name"])
        result = info if info else {"found": False, "message": "Sin recomendaciones registradas para esta especie."}

    else:
        result = {"error": f"Tool desconocida: {name}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
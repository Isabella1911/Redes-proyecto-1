from dotenv import load_dotenv
load_dotenv()

from clients import identify_plant_image, check_regional_occurrence
from knowledge_base import get_management_info

# 1. Probar identificación
result = identify_plant_image("test1.jpg")
print("Identify:", result)

# 2. Probar clasificación (usa un nombre científico real, ej. resultado de arriba)
if result.get("found"):
    occ = check_regional_occurrence(result["scientific_name"], "GT")
    print("Occurrence:", occ)

# 3. Probar knowledge base
mgmt = get_management_info("eichhornia crassipes")
print("Management:", mgmt)
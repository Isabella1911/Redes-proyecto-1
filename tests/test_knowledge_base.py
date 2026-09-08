from flora_mcp.knowledge_base import get_management_info, known_species


def test_lookup_is_case_and_whitespace_insensitive():
    info = get_management_info("  Pontederia   Crassipes ")
    assert info is not None
    assert info["urgency"] == "alta"
    assert info["methods"]


def test_synonym_resolves_to_the_accepted_entry():
    # Pl@ntNet still returns the old name; GBIF's backbone has moved on. Both
    # have to land on the same advice.
    old = get_management_info("Eichhornia crassipes")
    current = get_management_info("Pontederia crassipes")
    assert old == current
    assert old["scientific_name"] == "pontederia crassipes"


def test_unknown_species_returns_none_rather_than_a_guess():
    assert get_management_info("Quercus robur") is None


def test_known_species_lists_every_entry_sorted():
    species = known_species()
    assert species == sorted(species)
    assert "hydrilla verticillata" in species

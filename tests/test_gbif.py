"""The classification heuristic is the heart of this project, so it is tested
offline against stubbed GBIF responses. The handful of tests that hit the live
API are marked `network` -- run `pytest -m "not network"` to skip them.
"""

import pytest

from flora_mcp import gbif

COUNTRIES = (
    {"iso2": "GT", "iso3": "GTM", "title": "Guatemala"},
    {"iso2": "CR", "iso3": "CRI", "title": "Costa Rica"},
)


@pytest.fixture
def stub(monkeypatch):
    """Replace every network-touching helper with a controllable stub."""
    state = {
        "rows": [],
        "gisd": False,
        "griis": False,
        "occurrences": 0,
        "native": [],
    }

    monkeypatch.setattr(gbif, "_countries", lambda: COUNTRIES)
    monkeypatch.setattr(
        gbif,
        "match_species",
        lambda name: {
            "resolved": True,
            "input_name": name,
            "usage_key": 1,
            "accepted_key": 1,
            "scientific_name": f"{name} L.",
            "canonical_name": name,
            "rank": "SPECIES",
            "taxonomic_status": "ACCEPTED",
            "match_type": "EXACT",
            "confidence": 99,
            "family": "Testaceae",
            "kingdom": "Plantae",
        },
    )
    monkeypatch.setattr(gbif, "distributions_in_country", lambda m, iso2: state["rows"])
    monkeypatch.setattr(gbif, "in_gisd", lambda m: state["gisd"])
    monkeypatch.setattr(gbif, "in_country_griis", lambda m, title: state["griis"])
    monkeypatch.setattr(gbif, "occurrence_count", lambda m, iso2: state["occurrences"])
    monkeypatch.setattr(gbif, "native_range", lambda m, limit=25: state["native"])
    return state


def row(means, source=""):
    return {"establishment_means": means, "occurrence_status": "PRESENT", "source": source}


# --- country resolution ----------------------------------------------------


def test_resolve_country_accepts_iso2_iso3_and_name(monkeypatch):
    monkeypatch.setattr(gbif, "_countries", lambda: COUNTRIES)
    assert gbif.resolve_country("GT")["title"] == "Guatemala"
    assert gbif.resolve_country("gtm")["iso2"] == "GT"
    assert gbif.resolve_country("costa rica")["iso2"] == "CR"
    assert gbif.resolve_country("Guatem")["iso2"] == "GT"
    assert gbif.resolve_country("Narnia") is None


def test_classify_reports_an_unresolvable_place_instead_of_guessing(stub):
    result = gbif.classify_species("Pinus oocarpa", "Narnia")
    assert result["resolved"] is False
    assert "Narnia" in result["reason"]


# --- verdicts --------------------------------------------------------------


def test_national_checklist_native_row_wins(stub):
    stub["rows"] = [row("NATIVE")]
    stub["occurrences"] = 500
    result = gbif.classify_species("Pinus oocarpa", "Guatemala")
    assert result["status"] == "nativa"
    assert "establishmentMeans=NATIVE" in result["basis"]


def test_introduced_plus_gisd_listing_is_reported_as_invasive(stub):
    stub["rows"] = [row("INTRODUCED")]
    stub["gisd"] = True
    result = gbif.classify_species("Eichhornia crassipes", "GT")
    assert result["status"] == "invasora"
    assert "GISD" in result["basis"]


def test_introduced_without_a_gisd_listing_stays_introduced(stub):
    stub["rows"] = [row("INTRODUCED")]
    result = gbif.classify_species("Mangifera indica", "GT")
    assert result["status"] == "introducida"


def test_naturalised_counts_as_introduced(stub):
    stub["rows"] = [row("NATURALISED")]
    result = gbif.classify_species("Ricinus communis", "GT")
    assert result["status"] == "introducida"


def test_explicit_invasive_row_beats_everything(stub):
    stub["rows"] = [row("NATIVE"), row("INVASIVE")]
    result = gbif.classify_species("Casuarina equisetifolia", "GT")
    assert result["status"] == "invasora"


def test_a_non_native_row_outweighs_a_stale_native_one(stub):
    # Countries carry rows from several checklists; one lingering NATIVE record
    # should not make a naturalised alien look native.
    stub["rows"] = [row("NATIVE"), row("INTRODUCED")]
    result = gbif.classify_species("Leucaena leucocephala", "GT")
    assert result["status"] == "introducida"


def test_griis_membership_is_used_when_no_distribution_row_exists(stub):
    stub["griis"] = True
    result = gbif.classify_species("Hydrilla verticillata", "GT")
    assert result["status"] == "introducida"
    assert "GRIIS" in result["basis"]


def test_griis_plus_gisd_is_invasive(stub):
    stub["griis"] = True
    stub["gisd"] = True
    result = gbif.classify_species("Hydrilla verticillata", "GT")
    assert result["status"] == "invasora"


def test_occurrences_alone_do_not_imply_a_status(stub):
    stub["occurrences"] = 42
    result = gbif.classify_species("Pinus oocarpa", "GT")
    assert result["status"] == "presente, estatus no documentado"
    assert result["evidence"]["occurrence_records"] == 42


def test_no_evidence_at_all_says_so(stub):
    result = gbif.classify_species("Pinus oocarpa", "GT")
    assert result["status"] == "sin registros"


def test_evidence_travels_with_the_verdict(stub):
    stub["rows"] = [row("INTRODUCED", source="GRIIS Guatemala")]
    stub["gisd"] = True
    stub["native"] = ["BR", "AR"]
    result = gbif.classify_species("Eichhornia crassipes", "Guatemala")
    evidence = result["evidence"]
    assert evidence["distribution_rows"][0]["source"] == "GRIIS Guatemala"
    assert evidence["in_gisd"] is True
    assert evidence["native_range_sample"] == ["BR", "AR"]
    assert result["country_code"] == "GT"


# --- live API --------------------------------------------------------------


@pytest.mark.network
def test_live_match_resolves_a_synonym_to_its_accepted_name():
    match = gbif.match_species("Eichhornia crassipes")
    assert match["resolved"]
    assert match["taxonomic_status"] == "SYNONYM"
    # The synonym and the accepted name are different keys; both must be kept,
    # because checklists are indexed under either one.
    assert match["usage_key"] != match["accepted_key"]


@pytest.mark.network
def test_live_classification_of_a_known_invasive_in_guatemala():
    result = gbif.classify_species("Eichhornia crassipes", "Guatemala")
    assert result["resolved"]
    assert result["country_code"] == "GT"
    assert result["status"] in {"invasora", "introducida"}


@pytest.mark.network
def test_live_griis_checklist_exists_for_guatemala():
    assert gbif.griis_dataset_key("Guatemala") is not None

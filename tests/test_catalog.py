"""Offline registry integrity and candidate selection; fixtures below are synthetic."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.catalog import CatalogError, load_catalog
from src.catalog.catalog import DATA_DIR


@pytest.fixture
def snapshot(tmp_path):
    for filename in ("places.json", "sources.json"):
        (tmp_path / filename).write_bytes((DATA_DIR / filename).read_bytes())
    return tmp_path


def edit(root, filename, change):
    path = root / filename
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_shipped_snapshot_and_unknowns():
    catalog = load_catalog()
    result = catalog.search()
    assert len(result.places) == 5
    assert len(result.sources) == 13
    assert result.catalog_version.startswith("sha256:")
    assert all(s.checked_at.utcoffset() is not None for s in result.sources)
    garden = catalog.search(query="Ботанический").places[0]
    assert garden.entry_price.amount_kzt is None
    assert garden.entry_price.kind == "unknown"
    assert "932,14" in garden.entry_price.assumption
    assert garden.opening_hours is None
    assert all(p.fact_source_ids["visit_duration_minutes"] == [] for p in result.places)


def test_any_all_text_and_stable_order():
    catalog = load_catalog()
    assert len(catalog.search(interests=["nature"]).places) == 2
    assert len(catalog.search(interests=["nature", "history"]).places) == 4
    assert len(catalog.search(interests=["nature", "history"], match="all").places) == 1
    assert not catalog.search(interests=["food"]).places
    assert len(catalog.search(query="  КАСТЕЕВА  ").places) == 1
    assert len(catalog.search(query="самал-1").places) == 1
    assert not catalog.search(query="Несуществующий объект").places
    assert catalog.search().places == catalog.search().places


def test_date_filter_closed_unknown_open_and_range():
    catalog = load_catalog()
    assert len(catalog.search(start_date="2026-11-17").places) == 4  # Tuesday
    assert not catalog.search(start_date="2026-11-17", include_unknown_hours=False).places
    assert len(catalog.search(start_date="2026-11-18", include_unknown_hours=False).places) == 1
    assert len(catalog.search(start_date="2026-11-17", end_date="2026-11-18").places) == 5


def test_exception_overrides_weekly_and_null_is_not_closed(snapshot):
    def change(places):
        places[-1]["opening_hours"]["exceptions"] = {
            "2026-11-18": [], "2026-11-17": [{"start_time": "12:00", "end_time": "13:00"}],
            "2026-11-19": None,
        }
    edit(snapshot, "places.json", change)
    catalog = load_catalog(snapshot)
    assert len(catalog.search(start_date="2026-11-17", include_unknown_hours=False).places) == 1
    assert not catalog.search(start_date="2026-11-18", include_unknown_hours=False).places
    assert len(catalog.search(start_date="2026-11-19").places) == 5
    assert not catalog.search(start_date="2026-11-19", include_unknown_hours=False).places


@pytest.mark.parametrize("kwargs", [
    {"interests": ["shopping"]}, {"interests": ["culture", "culture"]},
    {"interests": "culture"}, {"query": None}, {"match": "bad"},
    {"end_date": "2026-11-17"}, {"start_date": "2026-02-30"},
    {"start_date": "2026-11-18", "end_date": "2026-11-17"},
    {"start_date": "2026-11-17", "end_date": "2026-11-20"},
    {"start_date": True}, {"include_unknown_hours": False},
    {"include_unknown_hours": "yes"},
])
def test_bad_search(kwargs):
    with pytest.raises(ValueError):
        load_catalog().search(**kwargs)


def test_only_related_sources_and_copies():
    catalog = load_catalog()
    selected = catalog.search(query="Ботанический")
    entities = {selected.places[0].place_id, selected.places[0].entry_price.basis_id}
    assert len(selected.sources) == 3
    assert all(f.entity_id in entities for s in selected.sources for f in s.supports)
    selected.places[0].name = "Synthetic mutation"
    selected.sources[0].supports.clear()
    assert len(catalog.search(query="Ботанический").sources[0].supports) > 0
    assert not catalog.search(query="Synthetic mutation").places
    assert catalog.search(query="absent").sources == ()


@pytest.mark.parametrize("filename,change", [
    ("places.json", lambda d: d.append(deepcopy(d[0]))),
    ("sources.json", lambda d: d.append(deepcopy(d[0]))),
    ("places.json", lambda d: d[1]["entry_price"].update(basis_id=d[0]["entry_price"]["basis_id"])),
    ("places.json", lambda d: d[0]["fact_source_ids"].update(name=["missing"])),
    ("places.json", lambda d: d[0]["fact_source_ids"].update(name=["botanical-official"])),
    ("places.json", lambda d: d[0]["fact_source_ids"].update(name=[])),
    ("sources.json", lambda d: d[0]["supports"][0].update(entity_id="absent")),
    ("places.json", lambda d: d[0]["interest_tags"].append("shopping")),
    ("places.json", lambda d: d[0]["entry_price"].update(amount_kzt=932.14)),
    ("places.json", lambda d: d[1]["entry_price"].update(amount_kzt=0)),
    ("places.json", lambda d: d[0].update(name="")),
    ("places.json", lambda d: d[0].update(unexpected=True)),
    ("places.json", lambda d: d[-1]["opening_hours"].update(source_ids=[])),
    ("places.json", lambda d: d[-1]["opening_hours"]["weekly"]["mon"].append(
        {"start_time": "17:00", "end_time": "19:00"})),
])
def test_bad_registry(snapshot, filename, change):
    edit(snapshot, filename, change)
    with pytest.raises(CatalogError):
        load_catalog(snapshot)


@pytest.mark.parametrize("payload", ['{', '{}', '[{"place_id":"a","place_id":"b"}]'])
def test_bad_json(snapshot, payload):
    (snapshot / "places.json").write_text(payload, encoding="utf-8")
    with pytest.raises(CatalogError):
        load_catalog(snapshot)


def test_missing_file_and_encoding(snapshot):
    (snapshot / "sources.json").unlink()
    with pytest.raises(CatalogError, match="sources.json"):
        load_catalog(snapshot)
    (snapshot / "sources.json").write_bytes(b"\xff")
    with pytest.raises(CatalogError):
        load_catalog(snapshot)


def test_default_path_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert len(load_catalog().search().places) == 5


def test_snapshot_version_tracks_both_files(snapshot):
    first = load_catalog(snapshot).version
    assert first == load_catalog(snapshot).version
    edit(snapshot, "sources.json", lambda d: d[0].update(title="Synthetic fixture title"))
    second = load_catalog(snapshot).version
    assert second != first
    edit(snapshot, "places.json", lambda d: d[0].update(visit_duration_minutes=91))
    assert load_catalog(snapshot).version != second


def test_cli_emits_utf8_even_with_windows_legacy_encoding():
    result = subprocess.run(
        [sys.executable, "-m", "src.catalog", "--query", "Кастеева"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        env=os.environ | {"PYTHONIOENCODING": "cp1252"}, check=True,
    )
    payload = json.loads(result.stdout.decode("utf-8"))
    assert len(payload["places"]) == 1
    assert "Кастеева" in payload["places"][0]["name"]

"""Load owner-maintained Place/Source registries and select candidates."""

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from typing import Literal, get_args

from pydantic import TypeAdapter, ValidationError

from src.contracts.models import Interest, Place, Source, parse_date

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class CatalogError(ValueError):
    """A catalogue snapshot is unreadable or internally inconsistent."""


@dataclass(frozen=True)
class CatalogSelection:
    places: tuple[Place, ...]
    sources: tuple[Source, ...]
    catalog_version: str


def _unique(items, attribute):
    result = {}
    for item in items:
        key = getattr(item, attribute)
        if key in result:
            raise CatalogError(f"Duplicate {attribute}: {key}")
        result[key] = item
    return result


class Catalog:
    def __init__(self, places: list[Place], sources: list[Source], version: str):
        self._places = tuple(places)
        self._sources = tuple(sources)
        self.version = version
        place_index = _unique(places, "place_id")
        source_index = _unique(sources, "source_id")
        basis_index = _unique([p.entry_price for p in places], "basis_id")
        if place_index.keys() & basis_index.keys():
            raise CatalogError("Place and cost basis IDs must not collide")
        entities = place_index.keys() | basis_index.keys()
        for source in sources:
            for fact in source.supports:
                if fact.entity_id not in entities:
                    raise CatalogError(f"Unknown supported entity: {fact.entity_id}")

        def check_refs(ids, entity_id, field, required=False):
            if len(ids) != len(set(ids)):
                raise CatalogError(f"Duplicate source reference: {entity_id}.{field}")
            if required and not ids:
                raise CatalogError(f"Missing evidence: {entity_id}.{field}")
            for source_id in ids:
                source = source_index.get(source_id)
                if source is None:
                    raise CatalogError(f"Unknown source: {source_id}")
                if not any(f.entity_id == entity_id and f.field == field for f in source.supports):
                    raise CatalogError(f"Unsupported reference: {source_id} -> {entity_id}.{field}")

        for place in places:
            for field, ids in place.fact_source_ids.items():
                if field not in Place.model_fields:
                    raise CatalogError(f"Unknown place fact field: {field}")
                if getattr(place, field) is None and ids:
                    raise CatalogError(f"Unknown fact cannot claim evidence: {place.place_id}.{field}")
                check_refs(ids, place.place_id, field)
            for field in ("name", "address", "coordinates"):
                check_refs(place.fact_source_ids.get(field, []), place.place_id, field,
                           required=getattr(place, field) is not None)
            if not place.interest_tags:
                raise CatalogError(f"Missing interest tags: {place.place_id}")
            if place.opening_hours is not None:
                check_refs(place.opening_hours.source_ids, place.place_id, "opening_hours", True)
                intervals = list(place.opening_hours.weekly.values()) + list(place.opening_hours.exceptions.values())
                for day in intervals:
                    if day:
                        ordered = sorted(day, key=lambda x: x.start_time)
                        if any(a.end_time > b.start_time for a, b in zip(ordered, ordered[1:])):
                            raise CatalogError(f"Overlapping opening intervals: {place.place_id}")
            basis = place.entry_price
            check_refs(basis.source_ids, basis.basis_id, "amount_kzt",
                       required=basis.kind == "published_price")

    def search(
        self, *, query: str = "", interests: list[Interest] | None = None,
        match: Literal["any", "all"] = "any", start_date: date | str | None = None,
        end_date: date | str | None = None, include_unknown_hours: bool = True,
    ) -> CatalogSelection:
        """Keep candidates open or unknown on at least one requested date.

        This checks day-level availability only, not visit time or trip feasibility.
        """
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        if interests is not None and not isinstance(interests, list):
            raise ValueError("interests must be a list")
        tags = interests or []
        if any(tag not in get_args(Interest) for tag in tags) or len(tags) != len(set(tags)):
            raise ValueError("Unknown or duplicate interest")
        if match not in ("any", "all") or type(include_unknown_hours) is not bool:
            raise ValueError("Invalid search mode")
        if start_date is None and end_date is not None:
            raise ValueError("end_date requires start_date")
        days = []
        if start_date is not None:
            start = parse_date(start_date)
            end = parse_date(end_date) if end_date is not None else start
            if not 0 <= (end - start).days <= 2:
                raise ValueError("Search must cover 1–3 inclusive days")
            days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        elif not include_unknown_hours:
            raise ValueError("Filtering unknown hours requires a date")

        def normalize(value):
            return " ".join(value.casefold().replace("ё", "е").split())

        def available(place):
            for day in days:
                hours = place.opening_hours
                intervals = None if hours is None else hours.exceptions.get(
                    day, hours.weekly.get(WEEKDAYS[day.weekday()]))
                if intervals or (intervals is None and include_unknown_hours):
                    return True
            return not days

        selected = []
        for place in self._places:
            overlap = set(tags) & set(place.interest_tags)
            if tags and (not overlap if match == "any" else len(overlap) != len(tags)):
                continue
            if normalize(query) not in normalize(place.name + " " + (place.address or "")):
                continue
            if available(place):
                selected.append(place)
        entities = {p.place_id for p in selected} | {p.entry_price.basis_id for p in selected}
        # Raw evidence also contains caveats that cannot fit normalized fields.
        sources = [s.model_copy(update={"supports": [f.model_copy(deep=True) for f in s.supports
                                                    if f.entity_id in entities]}, deep=True)
                   for s in self._sources if any(f.entity_id in entities for f in s.supports)]
        return CatalogSelection(tuple(p.model_copy(deep=True) for p in selected), tuple(sources), self.version)


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_catalog(data_dir: str | Path = DATA_DIR) -> Catalog:
    """Load a snapshot relative to this module, or from an explicit directory."""
    root = Path(data_dir)
    payloads = []
    parsed = []
    for filename, model in (("places.json", Place), ("sources.json", Source)):
        path = root / filename
        try:
            payload = path.read_bytes()
            raw = json.loads(payload.decode("utf-8-sig"), object_pairs_hook=_no_duplicate_keys)
            values = TypeAdapter(list[model]).validate_python(raw)
        except (OSError, UnicodeError, ValueError, ValidationError) as exc:
            raise CatalogError(f"Cannot load {path.name}: {exc}") from exc
        payloads.append(payload)
        parsed.append(values)
    version = "sha256:" + hashlib.sha256(b"\0".join(payloads)).hexdigest()
    return Catalog(*parsed, version)

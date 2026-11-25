"""Offline tests use synthetic responses; they do not prove Gemini access."""

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.ai.gemini import (
    ASSUMPTIONS, MODEL, PlannerError, Settings, generate, gemini_transport,
    load_settings, validate_draft,
)
from src.ai.__main__ import main
from src.catalog import load_catalog
from src.contracts.models import TripRequest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def context():
    req = TripRequest.model_validate_json((ROOT / "data/gemini-request.example.json").read_text())
    selection = load_catalog().search(interests=req.interests, start_date=req.start_date, end_date=req.end_date)
    p = next(p for p in selection.places if p.place_id == "almaty-central-museum")
    activity = dict(activity_id="a1", kind="visit", place_id=p.place_id,
        start_time="10:00", end_time="11:30", reason="invented price https://untrusted.invalid",
        source_ids=p.fact_source_ids["name"], cost_basis_ids=[p.entry_price.basis_id])
    raw = dict(days=[dict(date=str(req.start_date), activities=[activity], transfers=[])],
               assumptions=["Invented opening hours and price"])
    return req, selection, raw


def test_valid_and_untrusted_prose_removed(context):
    req, selection, raw = context
    draft, meta = generate(req, selection, Settings("synthetic"), transport=lambda *_: json.dumps(raw))
    assert "invented" not in draft.model_dump_json().lower()
    assert draft.assumptions == ASSUMPTIONS
    assert meta.mode == "ai" and meta.attempts == 1 and meta.model == MODEL
    assert meta.catalog_version == selection.catalog_version


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(price=0),
    lambda r: r["days"][0].update(date="2026-11-27"),
    lambda r: r["days"][0]["activities"][0].update(place_id="invented"),
    lambda r: r["days"][0]["activities"][0].update(source_ids=["kasteev-wikipedia"]),
    lambda r: r["days"][0]["activities"][0].update(source_ids=["invented"]),
    lambda r: r["days"][0]["activities"][0].update(cost_basis_ids=[]),
    lambda r: r["days"][0]["activities"][0].update(start_time="08:00", end_time="09:30"),
    lambda r: r["days"][0]["activities"][0].update(end_time="10:30"),
    lambda r: r["days"][0]["activities"][0].update(activity_id="https://untrusted.invalid"),
    lambda r: r["days"][0]["activities"][0].update(kind="meal"),
    lambda r: r["days"][0]["activities"][0].update(opening_hours="invented"),
    lambda r: r["days"][0]["activities"][0].update(end_time="25:00"),
    lambda r: r["days"][0]["activities"].append(dict(r["days"][0]["activities"][0], activity_id="a2")),
])
def test_rejects_invalid(context, mutation):
    req, selection, raw = context
    mutation(raw)
    with pytest.raises(PlannerError, match="INVALID_RESPONSE"):
        validate_draft(json.dumps(raw), req, selection)


@pytest.mark.parametrize("raw", ["not JSON", "{}", "[]", '{"days":[],"days":[],"assumptions":[]}', "x" * 100_001])
def test_malformed(context, raw):
    req, selection, _ = context
    with pytest.raises(PlannerError):
        validate_draft(raw, req, selection)


def test_bounded_correction(context):
    req, selection, raw = context
    calls = []
    def transport(settings, prompt, schema):
        calls.append(prompt)
        return "{}" if len(calls) == 1 else json.dumps(raw)
    _, meta = generate(req, selection, Settings("synthetic"), max_attempts=2, transport=transport)
    assert meta.attempts == 2 and len(calls) == 2
    assert "Предыдущий ответ" in calls[-1]
    with pytest.raises(PlannerError) as e:
        generate(req, selection, Settings("synthetic"), max_attempts=3, transport=lambda *_: "{}")
    assert e.value.code == "INVALID_RESPONSE" and e.value.attempts == 3


@pytest.mark.parametrize("code", ["QUOTA_EXHAUSTED", "SERVICE_UNAVAILABLE", "ACCESS_DENIED"])
def test_network_failures_are_not_retried(context, code):
    req, selection, _ = context
    calls = []
    def transport(*args):
        calls.append(1)
        raise PlannerError(code)
    with pytest.raises(PlannerError) as e:
        generate(req, selection, Settings("synthetic"), max_attempts=3, transport=transport)
    assert e.value.code == code and e.value.attempts == 1 and len(calls) == 1


def test_settings_do_not_leak_or_interpolate(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    path = tmp_path / ".env"
    with pytest.raises(PlannerError, match="MISSING_API_KEY"):
        load_settings(path)
    path.write_text("GEMINI_API_KEY=synthetic-${HOME}\nGEMINI_MODEL=" + MODEL)
    settings = load_settings(path)
    assert settings.api_key == "synthetic-${HOME}" and "synthetic" not in repr(settings)
    monkeypatch.setenv("GEMINI_API_KEY", "env-synthetic")
    assert load_settings(path).api_key == "env-synthetic"
    monkeypatch.setenv("GEMINI_MODEL", "paid-unapproved")
    with pytest.raises(PlannerError, match="UNSUPPORTED_MODEL"):
        load_settings(path)


@pytest.mark.parametrize("status,code", [(429,"QUOTA_EXHAUSTED"), (403,"ACCESS_DENIED"),
    (503,"SERVICE_UNAVAILABLE"), (404,"MODEL_UNAVAILABLE"), (400,"PROVIDER_REJECTED")])
def test_sdk_error_redaction_and_options(monkeypatch, status, code):
    from google import genai
    class ProviderFailure(Exception):
        status_code = status
    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["vertexai"] is False
            assert kwargs["http_options"].retry_options.attempts == 1
            self.interactions = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            assert kwargs["store"] is False and kwargs["timeout"] == 45
            assert "tools" not in kwargs
            raise ProviderFailure("synthetic-secret must never be exposed")
    monkeypatch.setattr(genai, "Client", FakeClient)
    with pytest.raises(PlannerError) as e:
        gemini_transport(Settings("synthetic-secret"), "prompt", {})
    assert str(e.value) == code and e.value.__suppress_context__


def test_cli_invalid_request_and_missing_key(tmp_path, monkeypatch, capsys):
    path = tmp_path / "request.json"
    path.write_text("{}")
    assert main(["--request", str(path)]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "INVALID_REQUEST"
    def missing(): raise PlannerError("MISSING_API_KEY")
    monkeypatch.setattr("src.ai.__main__.load_settings", missing)
    assert main(["--request", str(ROOT / "data/gemini-request.example.json")]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["error"] == "MISSING_API_KEY" and output["attempts"] == 0
    assert output["draft"] is None


def test_transfers_unknown_and_adjacent(context):
    req, selection, raw = context
    day = raw["days"][0]
    day["activities"].append(dict(activity_id="b1", kind="break", place_id=None,
        start_time="12:00", end_time="12:30", source_ids=[], cost_basis_ids=[], reason="break"))
    transfer = dict(from_activity_id="a1", to_activity_id="b1", duration_minutes=None,
                    method="unknown", cost_basis_ids=[])
    day["transfers"] = [transfer]
    assert validate_draft(json.dumps(raw), req, selection)
    for change in ({"duration_minutes": 10, "method": "catalog_estimate"},
                   {"cost_basis_ids": ["invented"]}, {"from_activity_id":"b1","to_activity_id":"a1"}):
        day["transfers"] = [dict(transfer, **change)]
        with pytest.raises(PlannerError): validate_draft(json.dumps(raw), req, selection)


def test_cli_success_enriches_only_catalog(context, monkeypatch, capsys):
    req, selection, raw = context
    result = generate(req, selection, Settings("synthetic"), transport=lambda *_: json.dumps(raw))
    monkeypatch.setattr("src.ai.__main__.load_settings", lambda: Settings("synthetic"))
    monkeypatch.setattr("src.ai.__main__.generate", lambda *a, **kw: result)
    assert main(["--request", str(ROOT / "data/gemini-request.example.json")]) == 0
    output = json.loads(capsys.readouterr().out)
    assert not output["verified_trip_result"]
    assert output["budget_status"] == output["schedule_status"] == "unknown"
    assert output["places"][0]["place_id"] == "almaty-central-museum"
    assert output["sources"] and "invented" not in json.dumps(output)


def test_three_days_and_missing_day(context):
    req, selection, raw = context
    req = req.model_copy(update={"end_date": req.start_date.replace(day=28)})
    with pytest.raises(PlannerError): validate_draft(json.dumps(raw), req, selection)
    places = [p for p in selection.places if p.place_id != "almaty-central-museum"][:2]
    for i, p in enumerate(places, 1):
        activity = dict(raw["days"][0]["activities"][0], activity_id=f"a{i+1}", place_id=p.place_id,
            source_ids=p.fact_source_ids["name"], cost_basis_ids=[p.entry_price.basis_id])
        raw["days"].append(dict(date=f"2026-11-{26+i}", activities=[activity], transfers=[]))
    assert len(validate_draft(json.dumps(raw), req, selection).days) == 3


@pytest.mark.parametrize("limit", [0, 4, True])
def test_no_call_for_invalid_limits(context, limit):
    req, selection, _ = context
    def forbidden(*_): pytest.fail("network should not be called")
    with pytest.raises(PlannerError):
        generate(req, selection, Settings("synthetic"), max_attempts=limit, transport=forbidden)


def test_no_call_for_empty_catalog_or_missing_key(context):
    req, selection, _ = context
    def forbidden(*_): pytest.fail("network should not be called")
    for selected, settings in ((replace(selection, places=()), Settings("synthetic")),
                               (selection, Settings(""))):
        with pytest.raises(PlannerError) as e:
            generate(req, selected, settings, transport=forbidden)
        assert e.value.attempts == 0


@pytest.mark.parametrize("response,valid", [
    (SimpleNamespace(status="completed", output_text="{}"), True),
    (SimpleNamespace(status="incomplete", output_text="{}"), False),
    (SimpleNamespace(status="completed", output_text=""), False),
    (SimpleNamespace(status="completed"), False),
])
def test_transport_response_shape(monkeypatch, response, valid):
    from google import genai
    class FakeClient:
        def __init__(self, **kwargs): self.interactions = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs): return response
    monkeypatch.setattr(genai, "Client", FakeClient)
    if valid:
        assert gemini_transport(Settings("synthetic"), "prompt", {}) == "{}"
    else:
        with pytest.raises(PlannerError, match="INVALID_RESPONSE"):
            gemini_transport(Settings("synthetic"), "prompt", {})

"""Offline orchestration through the real provider validator and schedule checker."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.ai import plan_with_schedule
from src.ai.gemini import MODEL, PlannerError, Settings, gemini_transport
from src.ai.planning import PROMPT_VERSION
from src.catalog import load_catalog
from src.contracts.models import TripRequest, TripResult
from src.schedule import TransferEstimate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def context():
    request = TripRequest.model_validate_json(
        (ROOT / "data/gemini-request.example.json").read_text(encoding="utf-8"))
    selection = load_catalog().search(interests=request.interests,
                                     start_date=request.start_date, end_date=request.end_date)
    place = next(p for p in selection.places if p.place_id == "almaty-central-museum")
    raw = {"days": [{"date": str(request.start_date), "activities": [{
        "activity_id": "a1", "kind": "visit", "place_id": place.place_id,
        "start_time": "10:00", "end_time": "11:30", "reason": "untrusted prose",
        "source_ids": place.fact_source_ids["name"],
        "cost_basis_ids": [place.entry_price.basis_id],
    }], "transfers": []}], "assumptions": ["untrusted hours"]}
    return request, selection, raw


def run(context, responses, **kwargs):
    request, selection, _ = context
    calls = []
    responses = iter(responses)

    def transport(settings, prompt, schema):
        calls.append(prompt)
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return json.dumps(response) if isinstance(response, dict) else response

    return plan_with_schedule(request, selection, Settings("synthetic"),
                              transport=transport, **kwargs), calls


def test_success_without_budget_or_trip_result(context):
    result, calls = run(context, [context[2]])
    assert len(calls) == result.metadata.attempts == 1
    assert result.status == "schedule_valid"
    assert result.schedule_check.status == "valid" and not result.schedule_check.issues
    assert result.metadata.mode == "ai" and result.metadata.model == MODEL
    assert result.metadata.prompt_version == PROMPT_VERSION
    assert result.metadata.catalog_version == context[1].catalog_version
    assert not isinstance(result, TripResult) and not hasattr(result, "budget")
    assert "untrusted" not in result.draft.model_dump_json()


@pytest.mark.parametrize("times,code", [
    (("08:00", "09:30"), "OUTSIDE_OPENING_HOURS"),
    (("10:00", "10:30"), "VISIT_TOO_SHORT"),
])
def test_repair_receives_structured_feedback(context, times, code):
    bad = deepcopy(context[2])
    bad["days"][0]["activities"][0].update(start_time=times[0], end_time=times[1])
    result, calls = run(context, [bad, context[2]])
    assert result.status == "schedule_valid" and result.metadata.attempts == len(calls) == 2
    feedback = json.loads(calls[1].splitlines()[-1])["previous_schedule"]
    assert feedback["draft"]["days"][0]["activities"][0]["start_time"] == times[0]
    assert feedback["known_violations"][0]["code"] == code
    assert feedback["known_violations"][0]["activity_id"] == "a1"
    assert feedback["known_violations"][0]["date"] == str(context[0].start_date)
    assert feedback["unknown_facts"] == []
    assert "synthetic" not in calls[1]


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_known_violations_exhaust_limit_without_claiming_infeasible(context, limit):
    bad = deepcopy(context[2])
    bad["days"][0]["activities"][0].update(start_time="08:00", end_time="09:30")
    result, calls = run(context, [bad] * limit, max_attempts=limit)
    assert result.status == "attempts_exhausted"
    assert result.schedule_check.status == "invalid"
    assert result.metadata.attempts == len(calls) == limit


def test_malformed_and_schedule_repairs_share_limit(context):
    bad = deepcopy(context[2])
    bad["days"][0]["activities"][0]["end_time"] = "10:30"
    result, calls = run(context, ["{}", bad, context[2]])
    assert result.status == "schedule_valid" and result.metadata.attempts == len(calls) == 3
    assert json.loads(calls[1].splitlines()[-1])["response_error"] == "INVALID_RESPONSE"
    assert json.loads(calls[2].splitlines()[-1])["previous_schedule"]["known_violations"]


@pytest.mark.parametrize("responses", [["{}"] * 3, [None, "{}", "{}"]])
def test_invalid_response_exhaustion_is_error_not_stale_draft(context, responses):
    if responses[0] is None:
        bad = deepcopy(context[2])
        bad["days"][0]["activities"][0]["end_time"] = "10:30"
        responses[0] = bad
    with pytest.raises(PlannerError) as caught:
        run(context, responses)
    assert caught.value.code == "INVALID_RESPONSE" and caught.value.attempts == 3


@pytest.mark.parametrize("code", ["QUOTA_EXHAUSTED", "SERVICE_UNAVAILABLE", "ACCESS_DENIED",
                                 "MODEL_UNAVAILABLE", "PROVIDER_REJECTED"])
@pytest.mark.parametrize("after_repair", [False, True])
def test_api_failure_is_propagated_immediately(context, code, after_repair):
    request, selection, raw = context
    calls = []
    bad = deepcopy(raw)
    bad["days"][0]["activities"][0]["end_time"] = "10:30"

    def transport(*_):
        calls.append(1)
        if after_repair and len(calls) == 1:
            return json.dumps(bad)
        raise PlannerError(code)

    with pytest.raises(PlannerError) as caught:
        plan_with_schedule(request, selection, Settings("synthetic"), transport=transport)
    assert caught.value.code == code
    assert caught.value.attempts == len(calls) == (2 if after_repair else 1)


def test_unknown_hours_stop_without_repair(context):
    request, selection, raw = context
    selection = replace(selection, places=tuple(
        p.model_copy(update={"opening_hours": None}) for p in selection.places))
    result, calls = run((request, selection, raw), [raw])
    assert result.status == result.schedule_check.status == "unknown"
    assert result.metadata.attempts == len(calls) == 1
    assert {i.code for i in result.schedule_check.issues} == {"UNKNOWN_OPENING_HOURS"}


def with_break(raw, *, overlap=False):
    raw = deepcopy(raw)
    day = raw["days"][0]
    day["activities"].append({"activity_id": "b1", "kind": "break", "place_id": None,
        "start_time": "11:00" if overlap else "12:00", "end_time": "12:30",
        "reason": "break", "source_ids": [], "cost_basis_ids": []})
    day["transfers"] = [{"from_activity_id": "a1", "to_activity_id": "b1",
        "duration_minutes": None, "method": "unknown", "cost_basis_ids": []}]
    return raw


def test_unknown_transfer_is_not_valid(context):
    result, calls = run(context, [with_break(context[2])])
    assert result.status == "unknown" and len(calls) == 1
    assert {i.code for i in result.schedule_check.issues} == {"UNKNOWN_TRANSFER_TIME"}
    assert result.draft.days[0].transfers[0].duration_minutes is None


def test_known_overlap_with_unknown_repairs_then_stops_unknown(context):
    result, calls = run(context, [with_break(context[2], overlap=True), with_break(context[2])])
    assert result.status == "unknown" and result.metadata.attempts == len(calls) == 2
    feedback = json.loads(calls[1].splitlines()[-1])["previous_schedule"]
    assert {i["code"] for i in feedback["known_violations"]} == {"TIME_OVERLAP"}
    assert {i["code"] for i in feedback["unknown_facts"]} == {"UNKNOWN_TRANSFER_TIME"}


def test_model_cannot_invent_transfer_estimate(context):
    bad = with_break(context[2])
    bad["days"][0]["transfers"][0].update(method="catalog_estimate", duration_minutes=0)
    result, calls = run(context, [bad, with_break(context[2])])
    assert result.status == "unknown" and len(calls) == 2
    assert json.loads(calls[1].splitlines()[-1])["response_error"] == "INVALID_RESPONSE"


def test_trusted_estimates_reach_model_and_checker(context):
    request, selection, raw = context
    first = selection.places[0]
    second = next(p for p in selection.places if p.place_id != first.place_id)
    # All hours in this fixture are synthetic, never changes to catalogue data.
    hours = next(p.opening_hours for p in selection.places if p.opening_hours)
    selection = replace(selection, places=tuple(
        p.model_copy(update={"opening_hours": hours, "visit_duration_minutes": 30})
        for p in (first, second)))
    raw = deepcopy(raw)
    day = raw["days"][0]
    for index, place in enumerate(selection.places):
        activity = dict(day["activities"][0], activity_id=f"a{index + 1}",
            place_id=place.place_id, start_time="10:00" if index == 0 else "10:30",
            end_time="10:30" if index == 0 else "11:00",
            source_ids=place.fact_source_ids["name"], cost_basis_ids=[place.entry_price.basis_id])
        if index == 0:
            day["activities"][0] = activity
        else:
            day["activities"].append(activity)
    day["transfers"] = [{"from_activity_id": "a1", "to_activity_id": "a2",
                         "method": "unknown", "duration_minutes": None, "cost_basis_ids": []}]
    fixed = deepcopy(raw)
    fixed["days"][0]["activities"][1].update(start_time="11:00", end_time="11:30")
    estimates = {(first.place_id, second.place_id): TransferEstimate(20, "Synthetic test estimate")}
    before = deepcopy((request, selection, estimates))
    result, calls = run((request, selection, raw), [raw, fixed], transfer_estimates=estimates)
    assert result.status == "schedule_valid" and len(calls) == 2
    context_payload = json.loads(calls[1].splitlines()[-1])
    assert context_payload["transfer_estimates"][0]["duration_minutes"] == 20
    assert context_payload["previous_schedule"]["known_violations"][0]["code"] == "INSUFFICIENT_TRANSFER_TIME"
    assert (request, selection, estimates) == before


@pytest.mark.parametrize("limit", [0, 4, True, 1.5])
def test_invalid_limit_without_call(context, limit):
    with pytest.raises(PlannerError) as caught:
        run(context, [], max_attempts=limit)
    assert caught.value.code == "CONFIG_ERROR" and caught.value.attempts == 0


def test_provider_sdk_has_no_nested_retries(context, monkeypatch):
    from google import genai
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["http_options"].retry_options.attempts == 1
            self.interactions = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(status="completed", output_text="{}")

    monkeypatch.setattr(genai, "Client", FakeClient)
    with pytest.raises(PlannerError) as caught:
        plan_with_schedule(context[0], context[1], Settings("synthetic"), transport=gemini_transport)
    assert caught.value.attempts == len(calls) == 3

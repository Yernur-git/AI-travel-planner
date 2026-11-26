"""Offline cases: modified catalogue values below are synthetic test data."""

from dataclasses import replace
from datetime import date
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.catalog import load_catalog
from src.contracts.models import OpeningHours, PlanDraft, TripRequest
from src.schedule import TransferEstimate, check_schedule

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def context():
    saved = json.loads((ROOT / "eval/results/gemini-first.json").read_text(encoding="utf-8"))
    return saved["request"], saved["draft"], load_catalog().search()


def run(context):
    request, raw, catalog = context
    return check_schedule(TripRequest.model_validate(request), PlanDraft.model_validate(raw), catalog)


def codes(check):
    return [issue.code for issue in check.issues]


def single(context):
    context[1]["days"][0]["activities"] = context[1]["days"][0]["activities"][:1]
    context[1]["days"][0]["transfers"] = []
    return context[1]["days"][0]["activities"][0]


def with_hours(context, weekly, exceptions=None):
    req, raw, catalog = context
    pid = raw["days"][0]["activities"][0]["place_id"]
    hours = OpeningHours(weekly=weekly, exceptions=exceptions or {}, source_ids=["synthetic"])
    places = tuple(p.model_copy(update={"opening_hours": hours}) if p.place_id == pid else p
                   for p in catalog.places)
    return req, raw, replace(catalog, places=places)


def test_saved_gemini_offline(context):
    before = json.dumps(context[1])
    result = run(context)
    assert result.status == "unknown"
    assert codes(result).count("UNKNOWN_OPENING_HOURS") == 1
    assert codes(result).count("UNKNOWN_TRANSFER_TIME") == 2
    assert json.dumps(context[1]) == before
    assert all(i.date == date(2026, 11, 26) and i.activity_id for i in result.issues)


def test_valid_single_visit(context):
    single(context)
    assert run(context).model_dump() == {"status": "valid", "issues": []}


@pytest.mark.parametrize("start,end,expected", [
    ("09:00", "10:30", "valid"), ("16:30", "18:00", "valid"),
    ("08:59", "10:30", "invalid"), ("16:30", "18:01", "invalid"),
    ("10:00", "11:29", "invalid"), ("10:00", "12:00", "valid"),
])
def test_visit_boundaries(context, start, end, expected):
    single(context).update(start_time=start, end_time=end)
    assert run(context).status == expected


@pytest.mark.parametrize("weekly,exceptions,status", [
    ({"thu": []}, {}, "invalid"), ({}, {}, "unknown"),
    ({"thu": None}, {}, "unknown"),
    ({"thu": []}, {"2026-11-26": [{"start_time": "09:00", "end_time": "18:00"}]}, "valid"),
    ({"thu": [{"start_time": "09:00", "end_time": "18:00"}]}, {"2026-11-26": []}, "invalid"),
    ({"thu": [{"start_time": "09:00", "end_time": "18:00"}]}, {"2026-11-26": None}, "unknown"),
    ({"thu": [{"start_time": "09:00", "end_time": "10:30"},
              {"start_time": "10:45", "end_time": "18:00"}]}, {}, "invalid"),
    ({"thu": [{"start_time": "10:30", "end_time": "18:00"},
              {"start_time": "09:00", "end_time": "10:30"}]}, {}, "valid"),
])
def test_hours_and_exception_precedence(context, weekly, exceptions, status):
    single(context)
    assert run(with_hours(context, weekly, exceptions)).status == status


def test_weekday_closed(context):
    single(context)
    context[0].update(start_date="2026-11-24", end_date="2026-11-24")
    context[1]["days"][0]["date"] = "2026-11-24"
    assert codes(run(context)) == ["OUTSIDE_OPENING_HOURS"]


@pytest.mark.parametrize("mutation,code", [
    (lambda r: r["days"][0].update(date="2026-11-27"), "MISSING_DAY"),
    (lambda r: r["days"][0]["activities"][0].update(place_id="absent"), "UNKNOWN_PLACE"),
    (lambda r: r["days"][0]["activities"][0].update(end_time="11:31"), "TIME_OVERLAP"),
    (lambda r: r["days"][0]["activities"][0].update(end_time="10:30"), "VISIT_TOO_SHORT"),
    (lambda r: r["days"][0]["activities"][0].update(start_time="08:00", end_time="09:30"), "OUTSIDE_OPENING_HOURS"),
    (lambda r: r["days"][0]["activities"][2].update(place_id="almaty-central-museum"), "REPEATED_PLACE"),
    (lambda r: r["days"][0]["transfers"].clear(), "MISSING_TRANSFER"),
    (lambda r: r["days"][0]["transfers"].append(r["days"][0]["transfers"][0].copy()), "DUPLICATE_TRANSFER"),
    (lambda r: r["days"][0]["transfers"][0].update(to_activity_id="visit-ykhlas-museum"), "INVALID_TRANSFER"),
])
def test_invalid_wins_over_unknown(context, mutation, code):
    mutation(context[1])
    result = run(context)
    assert result.status == "invalid"
    assert code in codes(result)
    assert "UNKNOWN_TRANSFER_TIME" in codes(result)


def test_out_of_order_and_nonadjacent_overlap(context):
    activities = context[1]["days"][0]["activities"]
    activities[0].update(start_time="10:00", end_time="14:00")
    activities[1].update(start_time="15:00", end_time="15:30")
    activities[2].update(start_time="12:00", end_time="13:00")
    result = run(context)
    assert result.status == "invalid"
    assert {"ACTIVITY_ORDER", "TIME_OVERLAP"} <= set(codes(result))


def test_unknown_place_for_meal(context):
    context[1]["days"][0]["activities"][1]["place_id"] = "absent"
    assert "UNKNOWN_PLACE" in codes(run(context))


def test_model_estimate_cannot_prove_transfer(context):
    for t in context[1]["days"][0]["transfers"]:
        t.update(method="catalog_estimate", duration_minutes=0)
    assert run(context).status == "unknown"


@pytest.mark.parametrize("gap,status", [(14, "invalid"), (15, "valid"), (16, "valid")])
def test_trusted_transfer_boundaries(context, gap, status):
    req, raw, catalog = context
    activities = raw["days"][0]["activities"]
    activities.pop(1)
    activities[1].update(place_id="almaty-kasteev-museum", start_time=f"11:{30 + gap:02}", end_time="14:00")
    raw["days"][0]["transfers"] = [dict(from_activity_id=activities[0]["activity_id"],
        to_activity_id=activities[1]["activity_id"], duration_minutes=None, method="unknown", cost_basis_ids=[])]
    hours = catalog.places[-1].opening_hours
    catalog = replace(catalog, places=tuple(p.model_copy(update={"opening_hours": hours}) for p in catalog.places))
    request, draft = TripRequest.model_validate(req), PlanDraft.model_validate(raw)
    estimates = {(activities[0]["place_id"], activities[1]["place_id"]): TransferEstimate(15, "Synthetic test estimate, not travel data.")}
    result = check_schedule(request, draft, catalog, transfer_estimates=estimates)
    assert result.status == status
    assert ("INSUFFICIENT_TRANSFER_TIME" in codes(result)) == (gap < 15)
    reversed_estimates = {(b, a): v for (a, b), v in estimates.items()}
    assert check_schedule(request, draft, catalog, transfer_estimates=reversed_estimates).status == "unknown"


@pytest.mark.parametrize("minutes,assumption", [(-1, "test"), (True, "test"), (1.5, "test"), (0, ""), (0, None)])
def test_bad_estimate(minutes, assumption):
    with pytest.raises(ValueError):
        TransferEstimate(minutes, assumption)


@pytest.mark.parametrize("length", [1, 2, 3])
def test_one_to_three_days_across_month_boundary(context, length):
    from datetime import timedelta
    single(context)
    start = date(2026, 11, 30)
    context[0].update(start_date=str(start), end_date=str(start + timedelta(days=length - 1)))
    template = context[1]["days"][0]
    context[1]["days"] = []
    for i in range(length):
        day = json.loads(json.dumps(template))
        day["date"] = str(start + timedelta(days=i))
        # A location-free break has no opening hours or visit-duration requirement.
        day["activities"][0].update(activity_id=f"break-{i}", kind="break", place_id=None)
        context[1]["days"].append(day)
    assert run(context).status == "valid"


def test_structural_errors_remain_contract_errors(context):
    single(context).update(start_time="12:00", end_time="11:00")
    with pytest.raises(ValidationError):
        run(context)

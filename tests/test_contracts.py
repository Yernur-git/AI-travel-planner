import json
from copy import deepcopy
from datetime import timedelta

import pytest
from pydantic import ValidationError

from src.contracts.models import (
    Activity, BudgetSummary, Coordinates, CostBasis, OpeningHours,
    Place, PlanDraft, ResultMetadata, Source, Transfer, TripRequest, TripResult,
)
from src.demo import build_demo


@pytest.fixture
def request_data():
    request, _ = build_demo()
    return request.model_dump(mode="json")


@pytest.fixture
def result_data():
    _, result = build_demo()
    return result.model_dump(mode="json")


def test_demo_roundtrip_and_provenance(result_data):
    result = TripResult.model_validate_json(json.dumps(result_data))
    assert result.metadata.mode == "demo"
    assert result.metadata.model is None
    assert result.metadata.attempts == 0
    assert result.sources == []
    assert result.status == "partial"
    assert result.budget.total_estimate_kzt is None
    assert result.schedule_check.status == "unknown"


@pytest.mark.parametrize("days", [1, 3])
def test_demo_issues_reference_activities_on_matching_dates(request_data, days):
    start_date = TripRequest.model_validate(request_data).start_date
    request_data["end_date"] = (start_date + timedelta(days=days - 1)).isoformat()
    request = TripRequest.model_validate(request_data)
    _, result = build_demo(request)

    activities_by_date = {
        day.date: {activity.activity_id for activity in day.activities}
        for day in result.itinerary
    }
    for issues in (result.budget.issues, result.schedule_check.issues):
        assert {issue.date for issue in issues} == set(activities_by_date)
        for issue in issues:
            assert issue.activity_id in activities_by_date[issue.date]


@pytest.mark.parametrize("days", [1, 2, 3])
def test_request_accepts_inclusive_lengths(request_data, days):
    request = TripRequest.model_validate(request_data)
    request_data["end_date"] = (request.start_date + timedelta(days=days - 1)).isoformat()
    assert TripRequest.model_validate(request_data)


@pytest.mark.parametrize("patch", [
    {"budget_kzt": 0}, {"budget_kzt": -1}, {"budget_kzt": True},
    {"budget_kzt": "10000"}, {"budget_kzt": 100.5},
    {"interests": []}, {"interests": ["walking", "walking"]},
    {"interests": ["shopping"]}, {"travelers": True}, {"travelers": 2},
    {"city": "Astana"}, {"currency": "USD"}, {"language": "en"},
    {"schema_version": "1.0-draft"}, {"extra": "unexpected"},
    {"start_date": "2026-02-30"}, {"start_date": 1234567890},
    {"start_date": "2026-11-17T00:00:00"},
])
def test_request_rejects_bad_inputs(request_data, patch):
    with pytest.raises(ValidationError):
        TripRequest.model_validate(request_data | patch)


@pytest.mark.parametrize("offset", [-1, 3])
def test_request_rejects_bad_range(request_data, offset):
    start = TripRequest.model_validate(request_data).start_date
    request_data["end_date"] = (start + timedelta(days=offset)).isoformat()
    with pytest.raises(ValidationError):
        TripRequest.model_validate(request_data)


@pytest.mark.parametrize("patch", [
    {"start_time": "25:00"}, {"start_time": "10:00:00"},
    {"end_time": "09:00"}, {"end_time": "10:00"}, {"place_id": None},
    {"total_kzt": 100},
])
def test_activity_rejects_invalid_model_output(result_data, patch):
    activity = result_data["itinerary"][0]["activities"][0]
    activity.pop("place_name")
    activity.pop("cost_item_ids")
    with pytest.raises(ValidationError):
        Activity.model_validate(activity | patch)


@pytest.mark.parametrize("change", ["ok", "total", "source", "dates", "unknown_ids", "over_budget"])
def test_result_rejects_false_success_or_broken_references(result_data, change):
    if change == "ok":
        result_data["status"] = "ok"
    elif change == "total":
        result_data["budget"]["total_estimate_kzt"] = 0
    elif change == "source":
        result_data["itinerary"][0]["activities"][0]["source_ids"] = ["missing"]
    elif change == "dates":
        result_data["itinerary"][0]["date"] = "2099-01-01"
    elif change == "unknown_ids":
        result_data["budget"]["unknown_cost_item_ids"] = []
    else:
        result_data["budget"]["budget_status"] = "over_budget"
    with pytest.raises(ValidationError):
        TripResult.model_validate(result_data)


def test_catalogue_shapes_and_unknown_hours():
    unknown = CostBasis(basis_id="test_entry", category="entry", amount_kzt=None,
                        kind="unknown", source_ids=[], assumption=None)
    hours = OpeningHours(weekly={"mon": [], "tue": None}, exceptions={}, source_ids=[])
    place = Place(place_id="test_place", name="Synthetic fixture", interest_tags=["walking"],
                  address=None, coordinates=None, visit_duration_minutes=60,
                  opening_hours=hours, entry_price=unknown, fact_source_ids={})
    assert place.opening_hours.weekly["mon"] == []
    assert place.opening_hours.weekly["tue"] is None
    with pytest.raises(ValidationError):
        Coordinates(latitude=91, longitude=0)
    with pytest.raises(ValidationError):
        CostBasis.model_validate(unknown.model_dump() | {"amount_kzt": 0})
    with pytest.raises(ValidationError):
        CostBasis.model_validate(unknown.model_dump() | {"amount_kzt": 0, "kind": "published_price"})


def test_source_requires_offset_and_http_url():
    # Reserved .invalid domain and timestamps are synthetic validation fixtures.
    source = dict(source_id="test_source", url="https://example.invalid/fixture",
                  title="Synthetic fixture", publisher="Test only",
                  checked_at="2026-01-01T00:00:00+05:00", published_at=None, valid_until=None,
                  supports=[dict(entity_id="test_place", field="name", value="Test")])
    assert Source.model_validate(source)
    for patch in ({"checked_at": "2026-01-01T00:00:00"}, {"url": "file:///secret"}):
        with pytest.raises(ValidationError):
            Source.model_validate(source | patch)


def test_draft_rejects_duplicate_activity_ids_and_missing_transfer_endpoint(result_data):
    day = deepcopy(result_data["itinerary"][0])
    day.pop("known_subtotal_kzt")
    day.pop("total_estimate_kzt")
    activity = day["activities"][0]
    activity.pop("place_name")
    activity.pop("cost_item_ids")
    assert PlanDraft(days=[day], assumptions=[])
    day["activities"].append(deepcopy(activity))
    with pytest.raises(ValidationError):
        PlanDraft(days=[day], assumptions=[])
    with pytest.raises(ValidationError):
        Transfer(from_activity_id="a", to_activity_id="b", duration_minutes=0,
                 method="unknown", cost_basis_ids=[])


def test_demo_cannot_claim_gemini_call():
    with pytest.raises(ValidationError):
        ResultMetadata(catalog_version=None, prompt_version=None, model="pretend-model",
                       attempts=1, mode="demo")


@pytest.mark.parametrize("status", ["service_error", "invalid_request", "infeasible"])
def test_non_plan_statuses(result_data, status):
    result_data.update(status=status, itinerary=None, budget=None, schedule_check=None,
                       request=None if status == "invalid_request" else result_data["request"],
                       errors=[dict(code="TEST_ONLY", message="Synthetic error fixture",
                                    field=None, activity_id=None)])
    assert TripResult.model_validate(result_data).status == status


def test_unknown_cost_is_not_a_free_trip(result_data):
    budget = result_data["budget"]
    budget["budget_status"] = "within_budget"
    with pytest.raises(ValidationError):
        BudgetSummary.model_validate(budget)


def test_known_subtotal_above_limit_cannot_claim_unknown(result_data):
    budget = result_data["budget"]
    budget["known_subtotal_kzt"] = budget["limit_kzt"] + 1
    with pytest.raises(ValidationError):
        BudgetSummary.model_validate(budget)

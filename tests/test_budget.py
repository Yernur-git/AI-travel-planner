from datetime import date, timedelta

import pytest

from src.budget import calculate_budget
from src.contracts.models import (
    Activity,
    CostBasis,
    DraftDay,
    PlanDraft,
    Transfer,
    TripRequest,
)


START_DATE = date(2026, 12, 1)


def make_request(days=1, budget=10_000):
    return TripRequest(
        schema_version="1.1-draft",
        start_date=START_DATE,
        end_date=START_DATE + timedelta(days=days - 1),
        budget_kzt=budget,
        interests=["culture"],
        city="Almaty",
        currency="KZT",
        travelers=1,
        language="ru",
    )


def basis(basis_id, category, amount, kind="editorial_estimate"):
    return CostBasis(
        basis_id=basis_id,
        category=category,
        amount_kzt=amount,
        kind=kind,
        source_ids=[],
        assumption="Synthetic test fixture; not a real-world price.",
    )


def visit(activity_id, cost_basis_ids=("ticket",)):
    return Activity(
        activity_id=activity_id,
        kind="visit",
        place_id=f"place-{activity_id}",
        start_time="10:00",
        end_time="11:00",
        reason="Test fixture",
        source_ids=[],
        cost_basis_ids=list(cost_basis_ids),
    )


def meal(activity_id="meal", cost_basis_ids=("meal-cost",)):
    return Activity(
        activity_id=activity_id,
        kind="meal",
        place_id=None,
        start_time="12:00",
        end_time="12:30",
        reason="Test fixture",
        source_ids=[],
        cost_basis_ids=list(cost_basis_ids),
    )


def day(day_date, activities, transfers=()):
    return DraftDay(date=day_date, activities=activities, transfers=list(transfers))


def one_day_plan(activities=None, transfers=None):
    activities = activities or [visit("visit"), meal()]
    if transfers is None:
        transfers = [
            Transfer(
                from_activity_id=activities[0].activity_id,
                to_activity_id=activities[1].activity_id,
                duration_minutes=None,
                method="unknown",
                cost_basis_ids=["ride"],
            )
        ] if len(activities) > 1 else []
    return PlanDraft(days=[day(START_DATE, activities, transfers)], assumptions=[])


def basic_bases(ticket_amount=100, meal_amount=50, ride_amount=25):
    return [
        basis("ticket", "entry", ticket_amount),
        basis("meal-cost", "food", meal_amount),
        basis("ride", "transport", ride_amount),
    ]


def test_exact_budget_equality_is_within_budget_and_quantity_is_applied():
    request = make_request(budget=175)
    result = calculate_budget(request, one_day_plan(), basic_bases())

    assert result.total_estimate_kzt == 175
    assert result.remaining_kzt == 0
    assert result.budget_status == "within_budget"
    assert all(item.quantity == request.travelers for item in result.items)
    assert all(item.amount_kzt == item.quantity * item.unit_amount_kzt for item in result.items)


def test_complete_total_above_budget_is_over_budget():
    result = calculate_budget(
        make_request(budget=174), one_day_plan(), basic_bases()
    )

    assert result.total_estimate_kzt == 175
    assert result.remaining_kzt == -1
    assert result.budget_status == "over_budget"


def test_unknown_price_stays_null_and_prevents_complete_total():
    bases = basic_bases()
    bases[1] = basis("meal-cost", "food", None, kind="unknown")

    result = calculate_budget(make_request(), one_day_plan(), bases)

    food_item = next(item for item in result.items if item.category == "food")
    assert food_item.unit_amount_kzt is None
    assert food_item.amount_kzt is None
    assert result.unknown_cost_item_ids == [food_item.cost_item_id]
    assert result.total_estimate_kzt is None
    assert result.remaining_kzt is None
    assert result.budget_status == "unknown"
    assert any(issue.code == "MISSING_COST" for issue in result.issues)


def test_known_subtotal_over_limit_is_over_budget_even_with_unknown_cost():
    bases = basic_bases()
    bases[1] = basis("meal-cost", "food", None, kind="unknown")

    result = calculate_budget(make_request(budget=124), one_day_plan(), bases)

    assert result.known_subtotal_kzt == 125
    assert result.total_estimate_kzt is None
    assert result.budget_status == "over_budget"


def test_zero_cost_is_known_and_not_treated_as_missing():
    result = calculate_budget(
        make_request(budget=1),
        one_day_plan(),
        basic_bases(ticket_amount=0, meal_amount=0, ride_amount=0),
    )

    assert result.total_estimate_kzt == 0
    assert result.remaining_kzt == 1
    assert result.budget_status == "within_budget"
    assert all(item.amount_kzt == 0 for item in result.items)
    assert result.unknown_cost_item_ids == []


def test_same_basis_on_distinct_days_is_counted_once_per_route_item():
    activities_by_day = [
        [visit("visit-1"), meal("meal-1")],
        [visit("visit-2"), meal("meal-2")],
    ]
    transfers = [
        Transfer(
            from_activity_id=activities[0].activity_id,
            to_activity_id=activities[1].activity_id,
            duration_minutes=None,
            method="unknown",
            cost_basis_ids=["ride"],
        )
        for activities in activities_by_day
    ]
    plan = PlanDraft(
        days=[
            day(START_DATE + timedelta(days=offset), activities, [transfer])
            for offset, (activities, transfer) in enumerate(zip(activities_by_day, transfers))
        ],
        assumptions=[],
    )

    result = calculate_budget(make_request(days=2), plan, basic_bases())

    assert result.total_estimate_kzt == 350
    assert result.budget_status == "within_budget"
    assert len(result.items) == 6
    assert [item.date for item in result.items].count(START_DATE) == 3
    assert [item.date for item in result.items].count(START_DATE + timedelta(days=1)) == 3
    assert sum(item.category == "entry" for item in result.items) == 2


def test_duplicate_basis_reference_is_counted_once_and_reported():
    plan = one_day_plan(activities=[visit("visit", ["ticket", "ticket"]), meal()])

    result = calculate_budget(make_request(), plan, basic_bases())

    ticket_items = [item for item in result.items if item.category == "entry"]
    assert len(ticket_items) == 1
    assert ticket_items[0].amount_kzt == 100
    assert any(issue.code == "DUPLICATE_COST_REFERENCE" for issue in result.issues)


def test_duplicate_transfer_record_is_counted_once_and_reported():
    activities = [visit("visit"), meal()]
    transfer = Transfer(
        from_activity_id="visit",
        to_activity_id="meal",
        duration_minutes=None,
        method="unknown",
        cost_basis_ids=["ride"],
    )
    plan = one_day_plan(activities=activities, transfers=[transfer, transfer.model_copy()])

    result = calculate_budget(make_request(), plan, basic_bases())

    assert result.total_estimate_kzt == 175
    assert sum(item.category == "transport" for item in result.items) == 1
    assert any(issue.code == "DUPLICATE_TRANSFER" for issue in result.issues)


def test_missing_daily_meal_and_transfer_are_unknown_with_machine_issues():
    activities = [visit("first"), visit("second")]
    result = calculate_budget(
        make_request(),
        one_day_plan(activities=activities, transfers=[]),
        basic_bases(),
    )

    assert result.total_estimate_kzt is None
    assert result.budget_status == "unknown"
    assert {issue.code for issue in result.issues} >= {
        "MISSING_DAILY_MEAL",
        "MISSING_TRANSFER",
    }
    assert sum(item.category == "food" for item in result.items) == 1
    assert sum(item.category == "transport" for item in result.items) == 1


def test_missing_or_wrong_category_basis_is_not_assumed_free():
    plan = one_day_plan(activities=[visit("visit", ["absent"]), meal()])
    supplied = [basis("absent", "food", 500), basis("meal-cost", "food", 50), basis("ride", "transport", 25)]

    result = calculate_budget(make_request(), plan, supplied)

    ticket = next(item for item in result.items if item.category == "entry")
    assert ticket.basis_id == "absent"
    assert ticket.amount_kzt is None
    assert {issue.code for issue in result.issues} >= {"COST_CATEGORY_MISMATCH"}
    assert result.total_estimate_kzt is None


def test_duplicate_registry_basis_ids_and_mismatched_dates_are_rejected():
    with pytest.raises(ValueError, match="Duplicate cost basis ID"):
        calculate_budget(make_request(), one_day_plan(), basic_bases() + [basic_bases()[0]])

    wrong_date = PlanDraft(
        days=[day(START_DATE + timedelta(days=1), [visit("visit"), meal()])],
        assumptions=[],
    )
    with pytest.raises(ValueError, match="Plan dates"):
        calculate_budget(make_request(), wrong_date, basic_bases())

"""Deterministic budget calculation over the shared 1.1-draft contract."""

import json
from collections.abc import Iterable
from datetime import date, timedelta

from src.contracts.models import (
    BudgetSummary,
    CostBasis,
    CostItem,
    Issue,
    PlanDraft,
    TripRequest,
)

__all__ = ["calculate_budget"]


def calculate_budget(
    request: TripRequest,
    plan: PlanDraft,
    cost_bases: Iterable[CostBasis],
) -> BudgetSummary:
    """Calculate route expenses using only supplied contract cost bases.

    Tickets, planned meals, and local transfers are charged once for each
    referenced basis and route item. A repeated basis ID on the same item is
    deduplicated and reported; using one basis on different route items is
    counted separately. ``quantity`` is the traveler count (currently one in
    TripRequest), and each missing price remains null rather than becoming
    free. A meal is required per day; if absent, its unknown placeholder is
    linked to the day's first activity only because CostItem requires an
    activity or transfer owner. Consumers should treat ``MISSING_DAILY_MEAL``
    as a day-level placeholder, not as the cost of that activity.

    Args:
        request: Validated trip request and total KZT limit.
        plan: Validated route draft. Its dates must exactly match the request.
        cost_bases: Catalog/registry CostBasis records referenced by the plan.

    Returns:
        A validated BudgetSummary with known subtotal, complete total and
        remaining balance when possible, plus machine-readable Issues.

    Raises:
        ValueError: If route dates differ from the request or cost basis IDs
            are duplicated in the supplied registry.
    """
    expected_dates = [
        request.start_date + timedelta(days=offset)
        for offset in range((request.end_date - request.start_date).days + 1)
    ]
    if [day.date for day in plan.days] != expected_dates:
        raise ValueError("Plan dates must exactly match the request")

    basis_index: dict[str, CostBasis] = {}
    for basis in cost_bases:
        if basis.basis_id in basis_index:
            raise ValueError(f"Duplicate cost basis ID: {basis.basis_id}")
        basis_index[basis.basis_id] = basis

    items: list[CostItem] = []
    issues: list[Issue] = []

    def add_issue(
        code: str,
        message: str,
        item_date: date,
        activity_id: str | None = None,
    ) -> None:
        issues.append(
            Issue(code=code, message=message, date=item_date, activity_id=activity_id)
        )

    def placeholder_basis_id(
        category: str,
        item_date: date,
        owner_ids: tuple[str, ...],
    ) -> str:
        seed = json.dumps(
            [category, item_date.isoformat(), *owner_ids],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        candidate = f"missing:{seed}"
        suffix = 0
        while candidate in basis_index:
            suffix += 1
            candidate = f"missing:{seed}:{suffix}"
        return candidate

    def add_item(
        *,
        item_date: date,
        category: str,
        basis_id: str,
        activity_id: str | None = None,
        from_activity_id: str | None = None,
        to_activity_id: str | None = None,
        issue_code: str | None = None,
        issue_message: str | None = None,
        issue_activity_id: str | None = None,
    ) -> None:
        basis = basis_index.get(basis_id)
        usable_basis = basis
        if basis is None:
            if issue_code is None:
                issue_code = "MISSING_COST_BASIS"
                issue_message = f"No cost basis record for {basis_id}."
            usable_basis = None
        elif basis.category != category:
            issue_code = "COST_CATEGORY_MISMATCH"
            issue_message = (
                f"Cost basis {basis_id} is {basis.category}, expected {category}."
            )
            usable_basis = None
        elif basis.kind == "unknown":
            issue_code = "MISSING_COST"
            issue_message = f"Cost basis {basis_id} has an unknown amount."

        if issue_code is not None:
            add_issue(
                issue_code,
                issue_message or "A required cost is unknown.",
                item_date,
                issue_activity_id if issue_activity_id is not None else activity_id,
            )

        quantity = request.travelers
        unit_amount = usable_basis.amount_kzt if usable_basis is not None else None
        amount = unit_amount * quantity if unit_amount is not None else None
        owner = (
            ["activity", activity_id]
            if activity_id is not None
            else ["transfer", from_activity_id, to_activity_id]
        )
        cost_item_id = json.dumps(
            [item_date.isoformat(), category, owner, basis_id],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        items.append(
            CostItem(
                cost_item_id=cost_item_id,
                date=item_date,
                activity_id=activity_id,
                from_activity_id=from_activity_id,
                to_activity_id=to_activity_id,
                category=category,
                basis_id=basis_id,
                quantity=quantity,
                unit_amount_kzt=unit_amount,
                amount_kzt=amount,
                kind=usable_basis.kind if usable_basis is not None else "unknown",
                source_ids=list(usable_basis.source_ids) if usable_basis is not None else [],
                assumption=usable_basis.assumption if usable_basis is not None else None,
            )
        )

    def unique_references(
        basis_ids: list[str],
        *,
        item_date: date,
        activity_id: str,
    ) -> list[str]:
        unique_ids: list[str] = []
        seen: set[str] = set()
        for basis_id in basis_ids:
            if basis_id in seen:
                add_issue(
                    "DUPLICATE_COST_REFERENCE",
                    f"Repeated cost basis reference {basis_id} was counted once.",
                    item_date,
                    activity_id,
                )
                continue
            seen.add(basis_id)
            unique_ids.append(basis_id)
        return unique_ids

    for day in plan.days:
        meal_activities = [activity for activity in day.activities if activity.kind == "meal"]
        for activity in day.activities:
            if activity.kind == "break":
                if activity.cost_basis_ids:
                    add_issue(
                        "UNEXPECTED_COST_REFERENCE",
                        "Break activities cannot carry budget cost references.",
                        day.date,
                        activity.activity_id,
                    )
                continue

            category = "entry" if activity.kind == "visit" else "food"
            basis_ids = unique_references(
                activity.cost_basis_ids,
                item_date=day.date,
                activity_id=activity.activity_id,
            )
            if not basis_ids:
                basis_id = placeholder_basis_id(
                    category, day.date, (activity.activity_id,)
                )
                add_item(
                    item_date=day.date,
                    category=category,
                    basis_id=basis_id,
                    activity_id=activity.activity_id,
                    issue_code="MISSING_COST",
                    issue_message=f"{category} cost is missing for {activity.activity_id}.",
                )
                continue

            for basis_id in basis_ids:
                add_item(
                    item_date=day.date,
                    category=category,
                    basis_id=basis_id,
                    activity_id=activity.activity_id,
                )

        if not meal_activities:
            anchor_activity = day.activities[0]
            basis_id = placeholder_basis_id("food", day.date, (anchor_activity.activity_id,))
            add_item(
                item_date=day.date,
                category="food",
                basis_id=basis_id,
                activity_id=anchor_activity.activity_id,
                issue_code="MISSING_DAILY_MEAL",
                issue_message=(
                    "No meal activity is planned for this day; daily food cost is unknown."
                ),
            )

        adjacent_pairs = [
            (first.activity_id, second.activity_id)
            for first, second in zip(day.activities, day.activities[1:])
        ]
        seen_transfers: set[tuple[str, str]] = set()
        for transfer in day.transfers:
            pair = (transfer.from_activity_id, transfer.to_activity_id)
            if pair in seen_transfers:
                add_issue(
                    "DUPLICATE_TRANSFER",
                    f"Repeated transfer {pair[0]} -> {pair[1]} was counted once.",
                    day.date,
                    transfer.from_activity_id,
                )
                continue
            seen_transfers.add(pair)
            if pair not in adjacent_pairs:
                add_issue(
                    "NON_ADJACENT_TRANSFER",
                    f"Transfer {pair[0]} -> {pair[1]} does not join adjacent activities.",
                    day.date,
                    transfer.from_activity_id,
                )

            basis_ids = unique_references(
                transfer.cost_basis_ids,
                item_date=day.date,
                activity_id=transfer.from_activity_id,
            )
            if not basis_ids:
                basis_id = placeholder_basis_id("transport", day.date, pair)
                add_item(
                    item_date=day.date,
                    category="transport",
                    basis_id=basis_id,
                    from_activity_id=pair[0],
                    to_activity_id=pair[1],
                    issue_code="MISSING_COST",
                    issue_message=(
                        f"Local transport cost is missing for {pair[0]} -> {pair[1]}."
                    ),
                    issue_activity_id=pair[0],
                )
                continue

            for basis_id in basis_ids:
                add_item(
                    item_date=day.date,
                    category="transport",
                    basis_id=basis_id,
                    from_activity_id=pair[0],
                    to_activity_id=pair[1],
                    issue_activity_id=pair[0],
                )

        for pair in adjacent_pairs:
            if pair in seen_transfers:
                continue
            basis_id = placeholder_basis_id("transport", day.date, pair)
            add_item(
                item_date=day.date,
                category="transport",
                basis_id=basis_id,
                from_activity_id=pair[0],
                to_activity_id=pair[1],
                issue_code="MISSING_TRANSFER",
                issue_message=(
                    f"No local transfer is recorded for {pair[0]} -> {pair[1]}."
                ),
                issue_activity_id=pair[0],
            )

    known_subtotal = sum(item.amount_kzt for item in items if item.amount_kzt is not None)
    unknown_ids = [item.cost_item_id for item in items if item.amount_kzt is None]
    total = None if unknown_ids else known_subtotal
    remaining = None if total is None else request.budget_kzt - total
    if unknown_ids:
        status = "over_budget" if known_subtotal > request.budget_kzt else "unknown"
    else:
        status = "over_budget" if total > request.budget_kzt else "within_budget"

    return BudgetSummary(
        currency=request.currency,
        limit_kzt=request.budget_kzt,
        items=items,
        known_subtotal_kzt=known_subtotal,
        unknown_cost_item_ids=unknown_ids,
        total_estimate_kzt=total,
        budget_status=status,
        remaining_kzt=remaining,
        issues=issues,
    )

"""Check a structurally validated draft against an owner-maintained catalogue."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

from src.catalog import CatalogSelection
from src.catalog.catalog import WEEKDAYS
from src.contracts.models import Issue, PlanDraft, ScheduleCheck, TripRequest


@dataclass(frozen=True)
class TransferEstimate:
    """Trusted caller-supplied estimate, never taken from model output.

    assumption records the method and origin, including applicability limits.
    This Python helper is not a new wire model or a catalogue field.
    """

    duration_minutes: int
    assumption: str

    def __post_init__(self):
        if type(self.duration_minutes) is not int or self.duration_minutes < 0:
            raise ValueError("Transfer estimate must be a nonnegative integer")
        if not isinstance(self.assumption, str) or not self.assumption.strip():
            raise ValueError("Transfer estimate needs its method and origin")


def _minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def check_schedule(
    request: TripRequest,
    draft: PlanDraft,
    catalog: CatalogSelection,
    *,
    transfer_estimates: Mapping[tuple[str, str], TransferEstimate] | None = None,
) -> ScheduleCheck:
    """Return all known violations and uncertainties, with invalid taking priority.

    Inputs must satisfy the existing contract. Pydantic errors are propagated;
    they are not missing factual data. Pass the full catalogue selection so a
    filtered-out place is not mistaken for an absent place. Optional estimates
    are directed (from_place_id, to_place_id) entries maintained by the caller.
    The function neither mutates inputs nor reads files, secrets or the network.
    """
    request = TripRequest.model_validate(request.model_dump())
    draft = PlanDraft.model_validate(draft.model_dump())
    places = {p.place_id: p for p in catalog.places}
    estimates = transfer_estimates or {}
    issues = []
    invalid = False

    def report(code, message, day=None, activity=None, *, unknown=False):
        nonlocal invalid
        invalid |= not unknown
        issues.append(Issue(code=code, message=message, date=day, activity_id=activity))

    expected = [request.start_date + timedelta(days=i)
                for i in range((request.end_date - request.start_date).days + 1)]
    actual = [day.date for day in draft.days]
    for date in expected:
        if date not in actual:
            report("MISSING_DAY", "Отсутствует день запроса.", date)
    for date in actual:
        if date not in expected:
            report("UNEXPECTED_DAY", "День вне дат запроса.", date)

    visited = set()
    for day in draft.days:
        for i, activity in enumerate(day.activities):
            aid = activity.activity_id
            if i and activity.start_time < day.activities[i - 1].start_time:
                report("ACTIVITY_ORDER", "Нарушен порядок начала активностей.", day.date, aid)
            for previous in day.activities[:i]:
                if max(previous.start_time, activity.start_time) < min(previous.end_time, activity.end_time):
                    report("TIME_OVERLAP", f"Пересечение с {previous.activity_id}.", day.date, aid)
            if activity.place_id is None:
                continue
            place = places.get(activity.place_id)
            if place is None:
                report("UNKNOWN_PLACE", "ID места отсутствует в каталоге.", day.date, aid)
                continue
            if activity.kind == "visit":
                if place.place_id in visited:
                    report("REPEATED_PLACE", "Повторный визит без структурированного основания.", day.date, aid)
                visited.add(place.place_id)
                duration = _minutes(activity.end_time) - _minutes(activity.start_time)
                if duration < place.visit_duration_minutes:
                    report("VISIT_TOO_SHORT", f"На визит нужно минимум {place.visit_duration_minutes} мин. по оценке каталога.", day.date, aid)
            hours = place.opening_hours
            intervals = None if hours is None else hours.exceptions.get(
                day.date, hours.weekly.get(WEEKDAYS[day.date.weekday()]))
            if intervals is None:
                report("UNKNOWN_OPENING_HOURS", "Часы на эту дату неизвестны.", day.date, aid, unknown=True)
            else:
                # Adjacent intervals form continuous opening time; a lunch gap does not.
                covered_until = activity.start_time
                for interval in sorted(intervals, key=lambda item: item.start_time):
                    if interval.start_time <= covered_until < interval.end_time:
                        covered_until = interval.end_time
                if covered_until < activity.end_time:
                    report("OUTSIDE_OPENING_HOURS", "Активность не помещается в часы работы.", day.date, aid)

        pairs = [(a.activity_id, b.activity_id) for a, b in zip(day.activities, day.activities[1:])]
        supplied = [(t.from_activity_id, t.to_activity_id) for t in day.transfers]
        counts = Counter(supplied)
        for pair, count in counts.items():
            if pair not in pairs:
                report("INVALID_TRANSFER", "Переход не соединяет соседние активности по порядку.", day.date, pair[1])
            if count > 1:
                report("DUPLICATE_TRANSFER", "Повтор перехода между активностями.", day.date, pair[1])
        for left, right in zip(day.activities, day.activities[1:]):
            pair = (left.activity_id, right.activity_id)
            if not counts[pair]:
                report("MISSING_TRANSFER", "Отсутствует переход между соседними активностями.", day.date, right.activity_id)
            estimate = None
            if left.place_id in places and right.place_id in places:
                estimate = estimates.get((left.place_id, right.place_id))
            if estimate is None:
                report("UNKNOWN_TRANSFER_TIME", "Нет независимой оценки времени перехода; число модели не подтверждает его.", day.date, right.activity_id, unknown=True)
            else:
                gap = _minutes(right.start_time) - _minutes(left.end_time)
                if gap < estimate.duration_minutes:
                    report("INSUFFICIENT_TRANSFER_TIME", f"Для перехода требуется {estimate.duration_minutes} мин. {estimate.assumption}", day.date, right.activity_id)

    return ScheduleCheck(status="invalid" if invalid else "unknown" if issues else "valid", issues=issues)

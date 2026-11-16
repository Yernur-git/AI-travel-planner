"""Wire formats only: catalogue checks and budget calculation live in owner modules."""

from datetime import date as Date, timedelta
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field,
    HttpUrl, StringConstraints, model_validator,
)

SCHEMA_VERSION = "1.1-draft"
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Money = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
Time = Annotated[str, StringConstraints(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]
Interest = Literal["culture", "history", "nature", "food", "walking"]
Category = Literal["entry", "food", "transport"]
CostKind = Literal["published_price", "editorial_estimate", "unknown"]
Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def parse_date(value: object) -> Date:
    if type(value) is Date:
        return value
    if isinstance(value, str):
        parsed = Date.fromisoformat(value)
        if parsed.isoformat() == value:
            return parsed
    raise ValueError("Use a date or YYYY-MM-DD, without time or numeric timestamp")


CalendarDate = Annotated[Date, BeforeValidator(parse_date)]


def require_unique(values: list, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label}")


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class TripRequest(ContractModel):
    schema_version: Literal["1.1-draft"]
    start_date: CalendarDate
    end_date: CalendarDate
    budget_kzt: PositiveInt
    interests: Annotated[list[Interest], Field(min_length=1)]
    city: Literal["Almaty"]
    currency: Literal["KZT"]
    travelers: Annotated[int, Field(strict=True, ge=1, le=1)]
    language: Literal["ru"]

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if not 0 <= (self.end_date - self.start_date).days <= 2:
            raise ValueError("Trip must cover 1–3 inclusive calendar days")
        require_unique(self.interests, "interests")
        return self


class SupportedFact(ContractModel):
    entity_id: Text
    field: Text
    value: Text


class Source(ContractModel):
    source_id: Text
    url: HttpUrl
    title: Text
    publisher: Text
    checked_at: AwareDatetime
    supports: Annotated[list[SupportedFact], Field(min_length=1)]
    published_at: AwareDatetime | None
    valid_until: AwareDatetime | None


class Coordinates(ContractModel):
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]


class TimeInterval(ContractModel):
    start_time: Time
    end_time: Time

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.start_time >= self.end_time:
            raise ValueError("start_time must precede end_time within one day")
        return self


class OpeningHours(ContractModel):
    weekly: dict[Weekday, list[TimeInterval] | None]
    exceptions: dict[CalendarDate, list[TimeInterval] | None]
    source_ids: list[Text]


class CostBasis(ContractModel):
    basis_id: Text
    category: Category
    amount_kzt: Money | None
    kind: CostKind
    source_ids: list[Text]
    assumption: Text | None

    @model_validator(mode="after")
    def validate_basis(self) -> Self:
        if (self.kind == "unknown") != (self.amount_kzt is None):
            raise ValueError("Unknown cost must be null; known cost must have an amount")
        if self.kind == "published_price" and not self.source_ids:
            raise ValueError("Published price needs a source")
        if self.kind == "editorial_estimate" and self.assumption is None:
            raise ValueError("Editorial estimate needs its rule and origin")
        return self


class Place(ContractModel):
    place_id: Text
    name: Text
    interest_tags: list[Interest]
    address: Text | None
    coordinates: Coordinates | None
    visit_duration_minutes: PositiveInt
    opening_hours: OpeningHours | None
    entry_price: CostBasis
    fact_source_ids: dict[Text, list[Text]]

    @model_validator(mode="after")
    def validate_entry(self) -> Self:
        if self.entry_price.category != "entry":
            raise ValueError("Place entry_price must have entry category")
        require_unique(self.interest_tags, "interest tags")
        return self


class Activity(TimeInterval):
    activity_id: Text
    kind: Literal["visit", "meal", "break"]
    place_id: Text | None
    reason: Text
    source_ids: list[Text]
    cost_basis_ids: list[Text]

    @model_validator(mode="after")
    def validate_visit(self) -> Self:
        if self.kind == "visit" and self.place_id is None:
            raise ValueError("Visit needs a catalogue place_id")
        return self


class Transfer(ContractModel):
    from_activity_id: Text
    to_activity_id: Text
    duration_minutes: Money | None
    method: Literal["catalog_estimate", "unknown"]
    cost_basis_ids: list[Text]

    @model_validator(mode="after")
    def validate_transfer(self) -> Self:
        if self.from_activity_id == self.to_activity_id:
            raise ValueError("Transfer must connect different activities")
        if (self.method == "unknown") != (self.duration_minutes is None):
            raise ValueError("Unknown transfer duration must be null")
        return self


class DraftDay(ContractModel):
    date: CalendarDate
    activities: Annotated[list[Activity], Field(min_length=1)]
    transfers: list[Transfer]

    @model_validator(mode="after")
    def validate_ids(self) -> Self:
        ids = [item.activity_id for item in self.activities]
        require_unique(ids, "activity IDs")
        for transfer in self.transfers:
            if not {transfer.from_activity_id, transfer.to_activity_id} <= set(ids):
                raise ValueError("Transfer references an absent activity")
        return self


class PlanDraft(ContractModel):
    days: Annotated[list[DraftDay], Field(min_length=1, max_length=3)]
    assumptions: list[Text]

    @model_validator(mode="after")
    def validate_days(self) -> Self:
        dates = [day.date for day in self.days]
        if dates != [dates[0] + timedelta(days=i) for i in range(len(dates))]:
            raise ValueError("Days must be consecutive and ordered")
        require_unique([a.activity_id for d in self.days for a in d.activities], "activity IDs")
        return self


class Issue(ContractModel):
    code: Text
    message: Text
    date: CalendarDate | None
    activity_id: Text | None


class ScheduleCheck(ContractModel):
    status: Literal["valid", "invalid", "unknown"]
    issues: list[Issue]


class CostItem(ContractModel):
    cost_item_id: Text
    date: CalendarDate
    activity_id: Text | None
    from_activity_id: Text | None
    to_activity_id: Text | None
    category: Category
    basis_id: Text
    quantity: PositiveInt
    unit_amount_kzt: Money | None
    amount_kzt: Money | None
    kind: CostKind
    source_ids: list[Text]
    assumption: Text | None

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        activity = self.activity_id is not None
        transfer = self.from_activity_id is not None and self.to_activity_id is not None
        partial_transfer = (self.from_activity_id is None) != (self.to_activity_id is None)
        if partial_transfer or activity == transfer:
            raise ValueError("Cost needs either an activity or a full transfer pair")
        if (self.kind == "unknown") != (self.amount_kzt is None):
            raise ValueError("Unknown cost must be null")
        if (self.unit_amount_kzt is None) != (self.amount_kzt is None):
            raise ValueError("Unit amount and amount must both be known or null")
        if self.kind == "published_price" and not self.source_ids:
            raise ValueError("Published price needs a source")
        if self.kind == "editorial_estimate" and self.assumption is None:
            raise ValueError("Editorial estimate needs an assumption")
        return self


class BudgetSummary(ContractModel):
    currency: Literal["KZT"]
    limit_kzt: PositiveInt
    items: Annotated[list[CostItem], Field(min_length=1)]
    known_subtotal_kzt: Money
    unknown_cost_item_ids: list[Text]
    total_estimate_kzt: Money | None
    budget_status: Literal["within_budget", "over_budget", "unknown"]
    remaining_kzt: Annotated[int, Field(strict=True)] | None
    issues: list[Issue]

    @model_validator(mode="after")
    def validate_unknowns(self) -> Self:
        require_unique([item.cost_item_id for item in self.items], "cost item IDs")
        require_unique(self.unknown_cost_item_ids, "unknown cost IDs")
        unknown = {item.cost_item_id for item in self.items if item.amount_kzt is None}
        if unknown != set(self.unknown_cost_item_ids):
            raise ValueError("unknown_cost_item_ids must match unknown items")
        if unknown:
            if self.total_estimate_kzt is not None or self.remaining_kzt is not None:
                raise ValueError("Incomplete budget cannot have a total or remaining amount")
            if self.budget_status == "within_budget":
                raise ValueError("Incomplete budget cannot be within_budget")
        elif self.total_estimate_kzt is None or self.remaining_kzt is None:
            raise ValueError("Complete budget needs total and remaining amount")
        if self.budget_status == "unknown" and not unknown:
            raise ValueError("Unknown budget needs unknown cost items")
        if unknown:
            expected = "over_budget" if self.known_subtotal_kzt > self.limit_kzt else "unknown"
        else:
            expected = "over_budget" if self.total_estimate_kzt > self.limit_kzt else "within_budget"
        if self.budget_status != expected:
            raise ValueError("Budget status contradicts supplied amount and limit")
        return self


class ResultActivity(Activity):
    place_name: Text | None
    cost_item_ids: list[Text]


class ResultDay(DraftDay):
    activities: Annotated[list[ResultActivity], Field(min_length=1)]
    known_subtotal_kzt: Money
    total_estimate_kzt: Money | None


class Notice(ContractModel):
    code: Text
    message: Text


class ResultError(Notice):
    field: Text | None
    activity_id: Text | None


class ResultMetadata(ContractModel):
    catalog_version: Text | None
    prompt_version: Text | None
    model: Text | None
    attempts: Annotated[int, Field(strict=True, ge=0)]
    mode: Literal["ai", "baseline", "demo"]

    @model_validator(mode="after")
    def validate_provenance(self) -> Self:
        if self.mode != "ai" and (self.model is not None or self.attempts != 0):
            raise ValueError("Demo/baseline cannot claim model calls")
        if self.mode == "ai" and self.attempts > 0:
            if None in (self.model, self.catalog_version, self.prompt_version):
                raise ValueError("AI call needs model, catalogue and prompt versions")
        return self


class TripResult(ContractModel):
    schema_version: Literal["1.1-draft"]
    status: Literal["ok", "partial", "infeasible", "invalid_request", "service_error"]
    message: Text
    request: TripRequest | None
    itinerary: Annotated[list[ResultDay], Field(min_length=1, max_length=3)] | None
    budget: BudgetSummary | None
    schedule_check: ScheduleCheck | None
    sources: list[Source]
    warnings: list[Notice]
    errors: list[ResultError]
    metadata: ResultMetadata

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        require_unique([source.source_id for source in self.sources], "source IDs")
        if self.status in {"invalid_request", "service_error"}:
            if any(v is not None for v in (self.itinerary, self.budget, self.schedule_check)):
                raise ValueError("Error response cannot contain a plan or checks")
            if not self.errors:
                raise ValueError("Error response needs errors")
        if self.status == "invalid_request" and self.request is not None:
            raise ValueError("Invalid request must be null")
        if self.status == "infeasible" and self.itinerary is not None:
            raise ValueError("Infeasible response cannot contain an itinerary")
        if self.status not in {"ok", "partial"}:
            return self
        if any(v is None for v in (self.request, self.itinerary, self.budget, self.schedule_check)):
            raise ValueError("Plan response needs request, itinerary and both checks")
        request, days, budget, schedule = self.request, self.itinerary, self.budget, self.schedule_check
        expected = [request.start_date + timedelta(days=i)
                    for i in range((request.end_date - request.start_date).days + 1)]
        if [day.date for day in days] != expected:
            raise ValueError("Itinerary must cover exactly the requested dates")
        if budget.limit_kzt != request.budget_kzt:
            raise ValueError("Budget limit must match request")
        if schedule.status == "invalid" or budget.budget_status == "over_budget":
            raise ValueError("Known invalid plan cannot be ok/partial")
        if self.status == "ok":
            if schedule.status != "valid" or budget.budget_status != "within_budget":
                raise ValueError("ok requires confirmed schedule and complete budget")
            if self.metadata.mode == "demo":
                raise ValueError("Synthetic demo cannot claim verified success")
        elif schedule.status == "valid" and budget.budget_status == "within_budget":
            raise ValueError("partial needs an unknown schedule or budget")
        activity_ids = [a.activity_id for d in days for a in d.activities]
        require_unique(activity_ids, "activity IDs")
        source_ids = {s.source_id for s in self.sources}
        cost_ids = {item.cost_item_id for item in budget.items}
        for day in days:
            for activity in day.activities:
                if not set(activity.source_ids) <= source_ids:
                    raise ValueError("Activity references an absent source")
                if not set(activity.cost_item_ids) <= cost_ids:
                    raise ValueError("Activity references an absent cost item")
        for item in budget.items:
            if not set(item.source_ids) <= source_ids:
                raise ValueError("Cost item references an absent source")
            linked = [v for v in (item.activity_id, item.from_activity_id, item.to_activity_id) if v]
            if not set(linked) <= set(activity_ids):
                raise ValueError("Cost item references an absent activity")
            if item.date not in expected:
                raise ValueError("Cost item date is outside the trip")
        return self

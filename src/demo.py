"""Synthetic contract example. No catalogue, provider or calculation is called."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.contracts.models import SCHEMA_VERSION, TripRequest, TripResult


def build_demo(request: TripRequest | None = None) -> tuple[TripRequest, TripResult]:
    if request is None:
        day = (datetime.now(ZoneInfo("Asia/Almaty")) + timedelta(days=1)).date()
        request = TripRequest(
            schema_version=SCHEMA_VERSION,
            start_date=day, end_date=day, budget_kzt=10000,
            interests=["walking"], city="Almaty", currency="KZT", travelers=1, language="ru",
        )

    items = []
    days = []
    for day_index in range((request.end_date - request.start_date).days + 1):
        day = request.start_date + timedelta(days=day_index)
        activity_id = f"demo_activity_{day_index + 1}"
        day_items = [
            {
                "cost_item_id": f"demo_cost_{day_index + 1}_{category}", "date": day,
                "activity_id": activity_id, "from_activity_id": None,
                "to_activity_id": None, "category": category,
                "basis_id": f"demo_basis_{day_index + 1}_{category}", "quantity": 1,
                "unit_amount_kzt": None, "amount_kzt": None, "kind": "unknown",
                "source_ids": [], "assumption": None,
            }
            for category in ("entry", "food", "transport")
        ]
        items.extend(day_items)
        days.append({
            "date": day,
            "activities": [{
                "activity_id": activity_id, "kind": "visit",
                "place_id": f"demo_place_{day_index + 1}",
                "place_name": "Условное место — учебная запись",
                "start_time": "10:00", "end_time": "11:00",
                "reason": "Показывает структуру прогулки; это не рекомендация реального места.",
                "source_ids": [],
                "cost_basis_ids": [item["basis_id"] for item in day_items],
                "cost_item_ids": [item["cost_item_id"] for item in day_items],
            }],
            "transfers": [], "known_subtotal_kzt": 0, "total_estimate_kzt": None,
        })

    result = TripResult.model_validate({
        "schema_version": SCHEMA_VERSION,
        "status": "partial",
        "message": "Демонстрационный результат. Это учебные данные, не ответ Gemini.",
        "request": request,
        "itinerary": days,
        "budget": {
            "currency": "KZT", "limit_kzt": request.budget_kzt,
            "items": items, "known_subtotal_kzt": 0,
            "unknown_cost_item_ids": [item["cost_item_id"] for item in items],
            "total_estimate_kzt": None, "budget_status": "unknown", "remaining_kzt": None,
            "issues": [
                {
                    "code": "MISSING_COST", "message": "Цены в демо неизвестны.",
                    "date": day["date"], "activity_id": day["activities"][0]["activity_id"],
                }
                for day in days
            ],
        },
        "schedule_check": {
            "status": "unknown",
            "issues": [
                {
                    "code": "UNKNOWN_OPENING_HOURS",
                    "message": "В демо нет проверенных часов работы.",
                    "date": day["date"], "activity_id": day["activities"][0]["activity_id"],
                }
                for day in days
            ],
        },
        "sources": [],
        "warnings": [{"code": "DEMO_DATA", "message": "Место условное. Источников нет. "
                      "Расходы и расписание не проверены; Gemini не вызывался."}],
        "errors": [],
        "metadata": {"catalog_version": None, "prompt_version": None,
                     "model": None, "attempts": 0, "mode": "demo"},
    })
    return request, result

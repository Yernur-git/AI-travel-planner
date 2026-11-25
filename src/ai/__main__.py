"""Run with python -m src.ai; output is diagnostic, not a shared TripResult."""

import argparse
import json
from pathlib import Path
import sys

from pydantic import ValidationError

from src.ai.gemini import PlannerError, generate, load_settings
from src.catalog import CatalogError, load_catalog
from src.contracts.models import TripRequest

MESSAGES = {
    "MISSING_API_KEY": "Задайте GEMINI_API_KEY локально в .env или окружении.",
    "CONFIG_ERROR": "Не удалось прочитать настройки или неверный предел попыток.",
    "UNSUPPORTED_MODEL": "Разрешена только проверенная по тарифу gemini-3.5-flash-lite.",
    "ACCESS_DENIED": "Gemini отказал в доступе. Проверьте ключ и права проекта в AI Studio.",
    "QUOTA_EXHAUSTED": "Квота Gemini исчерпана. Проверьте лимиты Free; платный тариф не подключается.",
    "MODEL_UNAVAILABLE": "Модель недоступна этому проекту.",
    "PROVIDER_REJECTED": "Gemini отклонил запрос. Проверьте совместимость API и схему.",
    "SERVICE_UNAVAILABLE": "Gemini недоступен или истекло время ожидания. Повторите позже.",
    "INVALID_RESPONSE": "Ответ Gemini не прошёл проверку. Маршрут не выдан.",
    "EMPTY_CATALOG_SELECTION": "В каталоге нет подходящих мест для этого запроса.",
    "INVALID_REQUEST": "Запрос должен соответствовать TripRequest 1.1-draft.",
    "CATALOG_ERROR": "Не удалось загрузить каталог.",
}


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Настоящий вызов Gemini; бюджет не рассчитывается.")
    parser.add_argument("--request", type=Path, required=True, help="JSON TripRequest")
    parser.add_argument("--max-attempts", type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args(argv)
    try:
        try:
            request = TripRequest.model_validate_json(args.request.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError, ValidationError):
            raise PlannerError("INVALID_REQUEST") from None
        settings = load_settings()
        try:
            selection = load_catalog().search(interests=request.interests,
                start_date=request.start_date, end_date=request.end_date)
        except CatalogError:
            raise PlannerError("CATALOG_ERROR") from None
        draft, metadata = generate(request, selection, settings, max_attempts=args.max_attempts)
        used_places = {a.place_id for d in draft.days for a in d.activities if a.place_id}
        places = [p for p in selection.places if p.place_id in used_places]
        used_sources = {s for d in draft.days for a in d.activities for s in a.source_ids}
        for place in places:
            used_sources.update(place.entry_price.source_ids)
            for refs in place.fact_source_ids.values():
                used_sources.update(refs)
            if place.opening_hours:
                used_sources.update(place.opening_hours.source_ids)
        output = {"diagnostic": "gemini_plan_draft", "verified_trip_result": False,
            "request": request.model_dump(mode="json"), "draft": draft.model_dump(mode="json"),
            "metadata": metadata.model_dump(mode="json"),
            "places": [p.model_dump(mode="json") for p in places],
            "sources": [s.model_dump(mode="json") for s in selection.sources if s.source_id in used_sources],
            "budget_status": "unknown", "schedule_status": "unknown"}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except PlannerError as exc:
        print(json.dumps({"diagnostic": "gemini_plan_draft", "error": exc.code,
            "message": MESSAGES[exc.code], "attempts": exc.attempts,
            "draft": None}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

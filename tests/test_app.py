import json
from pathlib import Path
from datetime import date, timedelta

import pytest
from streamlit.testing.v1 import AppTest

from src.demo import build_demo


def _result_fixture(status):
    request, result = build_demo()
    payload = result.model_dump(mode="json")
    payload["message"] = f"Синтетический тестовый пример статуса {status}."

    if status == "ok":
        first_activity = payload["itinerary"][0]["activities"][0]
        meal_id = "app_test_meal"
        payload["itinerary"][0]["activities"].append(
            {
                "activity_id": meal_id,
                "kind": "meal",
                "place_id": None,
                "place_name": "Условный обед — тест",
                "start_time": "12:00",
                "end_time": "12:30",
                "reason": "Синтетические данные для AppTest.",
                "source_ids": [],
                "cost_basis_ids": [],
                "cost_item_ids": [],
            }
        )
        transport = next(item for item in payload["budget"]["items"] if item["category"] == "transport")
        transport.update(
            activity_id=None,
            from_activity_id=first_activity["activity_id"],
            to_activity_id=meal_id,
        )
        food = next(item for item in payload["budget"]["items"] if item["category"] == "food")
        food["activity_id"] = meal_id
        first_activity["cost_item_ids"] = [
            item["cost_item_id"]
            for item in payload["budget"]["items"]
            if item["activity_id"] == first_activity["activity_id"]
        ]
        first_activity["cost_basis_ids"] = [
            item["basis_id"]
            for item in payload["budget"]["items"]
            if item["activity_id"] == first_activity["activity_id"]
        ]
        payload["itinerary"][0]["activities"][1]["cost_item_ids"] = [food["cost_item_id"]]
        payload["itinerary"][0]["activities"][1]["cost_basis_ids"] = [food["basis_id"]]
        payload["itinerary"][0]["transfers"] = [
            {
                "from_activity_id": first_activity["activity_id"],
                "to_activity_id": meal_id,
                "duration_minutes": 15,
                "method": "catalog_estimate",
                "cost_basis_ids": [],
            }
        ]
        for item in payload["budget"]["items"]:
            item.update(
                unit_amount_kzt=100,
                amount_kzt=100,
                kind="editorial_estimate",
                assumption="Синтетические данные для AppTest.",
            )
        total = sum(item["amount_kzt"] for item in payload["budget"]["items"])
        payload["budget"].update(
            known_subtotal_kzt=total,
            unknown_cost_item_ids=[],
            total_estimate_kzt=total,
            budget_status="within_budget",
            remaining_kzt=request.budget_kzt - total,
            issues=[],
        )
        for day in payload["itinerary"]:
            day_total = sum(
                item["amount_kzt"]
                for item in payload["budget"]["items"]
                if item["date"] == day["date"]
            )
            day.update(known_subtotal_kzt=day_total, total_estimate_kzt=day_total)
        payload["schedule_check"] = {"status": "valid", "issues": []}
        payload["status"] = "ok"
        payload["sources"] = [
            {
                "source_id": "app_test_source",
                "url": "https://example.invalid/app-test",
                "title": "Синтетический источник",
                "publisher": "AppTest",
                "checked_at": "2026-01-01T00:00:00+05:00",
                "published_at": None,
                "valid_until": None,
                "supports": [
                    {
                        "entity_id": payload["itinerary"][0]["activities"][0]["place_id"],
                        "field": "name",
                        "value": "Тестовое место",
                    }
                ],
            }
        ]
        payload["itinerary"][0]["activities"][0]["source_ids"] = ["app_test_source"]
        next(item for item in payload["budget"]["items"] if item["category"] == "entry")[
            "source_ids"
        ] = ["app_test_source"]
        payload["metadata"].update(
            mode="ai",
            model="synthetic-app-test-fixture",
            catalog_version="synthetic-app-test-catalog",
            prompt_version="synthetic-app-test-prompt",
            attempts=1,
        )
    elif status not in {"partial"}:
        payload.update(
            status=status,
            request=None if status == "invalid_request" else payload["request"],
            itinerary=None,
            budget=None,
            schedule_check=None,
            sources=[],
            warnings=[],
            errors=[
                {
                    "code": f"TEST_{status.upper()}",
                    "message": f"Синтетическая ошибка для {status}.",
                    "field": "start_date" if status == "invalid_request" else None,
                    "activity_id": None,
                }
            ],
        )
    return payload


def test_trip_form_submits_to_explicit_demo_and_clears_old_result_on_error():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    assert not app.exception
    assert "Gemini не подключён" in app.warning[0].value
    assert any("жильё и дорога до Алматы исключены" in item.value for item in app.caption)
    app.date_input(key="start_date").set_value(date(2026, 12, 1))
    app.date_input(key="end_date").set_value(date(2026, 12, 2))
    app.number_input(key="budget_kzt").set_value(25000)
    app.multiselect(key="interests").set_value(["culture", "food"])
    app.form_submit_button(key="submit_trip").click().run()
    assert not app.exception
    assert len(app.json) == 1
    assert any("не ответ Gemini" in item.value for item in app.markdown)
    result = json.loads(app.json[0].value)
    assert result["metadata"]["mode"] == "demo"
    assert result["request"]["budget_kzt"] == 25000
    assert result["request"]["interests"] == ["culture", "food"]
    assert len(result["itinerary"]) == 2

    app.date_input(key="end_date").set_value(date(2026, 11, 30))
    app.form_submit_button(key="submit_trip").click().run()
    assert not app.exception
    assert "не может быть раньше" in app.error[0].value
    assert len(app.json) == 0
    assert not any(item.value == "Демонстрационный результат" for item in app.subheader)


def test_trip_form_rejects_more_than_three_days():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    start_date = date(2026, 12, 1)
    app.date_input(key="start_date").set_value(start_date)
    app.date_input(key="end_date").set_value(start_date)
    app.form_submit_button(key="submit_trip").click().run()
    assert len(app.json) == 1

    app.date_input(key="end_date").set_value(start_date + timedelta(days=3))
    app.form_submit_button(key="submit_trip").click().run()
    assert not app.exception
    assert "от 1 до 3 календарных дней" in app.error[0].value
    assert len(app.json) == 0


def test_trip_form_rejects_end_date_before_start_date():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    start_date = date(2026, 12, 2)
    app.date_input(key="start_date").set_value(start_date)
    app.date_input(key="end_date").set_value(start_date - timedelta(days=1))
    app.form_submit_button(key="submit_trip").click().run()
    assert not app.exception
    assert "не может быть раньше" in app.error[0].value
    assert len(app.json) == 0


def test_trip_form_requires_an_interest():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    app.multiselect(key="interests").set_value([])
    app.form_submit_button(key="submit_trip").click().run()
    assert not app.exception
    assert "Выберите хотя бы один интерес" in app.error[0].value
    assert len(app.json) == 0


@pytest.mark.parametrize(
    ("status", "expected_heading"),
    [
        ("ok", "Маршрут проверен"),
        ("partial", "Маршрут проверен частично"),
        ("infeasible", "Не удалось составить допустимый маршрут"),
        ("invalid_request", "Проверьте параметры запроса"),
        ("service_error", "Ошибка сервиса"),
    ],
)
def test_app_displays_every_contract_status_as_synthetic_fixture(status, expected_heading):
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
    app.session_state["trip_result"] = _result_fixture(status)
    app.session_state["test_fixture"] = True
    app.run()

    assert not app.exception
    assert any(item.value == expected_heading for item in app.subheader)
    assert any("ТЕСТОВЫЙ ПРИМЕР" in item.value for item in app.warning)
    if status == "partial":
        rendered = "\n".join(str(item.value) for item in app.get("markdown"))
        rendered += "\n" + "\n".join(str(item.value) for item in app.get("write"))
        assert "Итоговая оценка: неизвестна" in rendered
        assert "сумма неизвестна" in rendered
        assert "Источники не указаны." in rendered
        assert "Итоговая оценка: 0 KZT" not in rendered
        note = "только подтверждённая часть; это не значит, что поездка бесплатна"
        assert any(note in item.value for item in app.caption)
        assert any(note in item.value for item in app.markdown)
    if status == "ok":
        assert any("https://example.invalid/app-test" in item.value for item in app.markdown)
        assert any("Синтетический источник" in item.value for item in app.markdown)
        assert any("10:00–11:00" in item.value and "Условное место" in item.value for item in app.markdown)
        assert any("Условный обед — тест" in item.value for item in app.markdown)
        assert any("15 мин" in item.value for item in app.caption)
        assert any("Итоговая оценка: 300 KZT" in item.value for item in app.markdown)
        assert not any(
            "это не значит, что поездка бесплатна" in item.value
            for item in [*app.caption, *app.markdown]
        )
    if status in {"infeasible", "invalid_request", "service_error"}:
        assert any("Синтетическая ошибка" in item.value for item in app.error)
        assert not any(item.value == "Маршрут по дням" for item in app.markdown)

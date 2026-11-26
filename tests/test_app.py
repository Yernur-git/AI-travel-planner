import json
from pathlib import Path
from datetime import date, timedelta

from streamlit.testing.v1 import AppTest


def test_trip_form_submits_to_explicit_demo():
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
    assert "не ответ Gemini" in app.info[0].value
    result = json.loads(app.json[0].value)
    assert result["metadata"]["mode"] == "demo"
    assert result["request"]["budget_kzt"] == 25000
    assert result["request"]["interests"] == ["culture", "food"]
    assert len(result["itinerary"]) == 2


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

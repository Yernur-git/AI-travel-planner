import streamlit as st
from pydantic import ValidationError

from src.demo import build_demo
from src.contracts.models import SCHEMA_VERSION, TripRequest, TripResult
from src.ui.results import render_trip_result

st.set_page_config(page_title="AI Travel Planner", page_icon=None)
st.title("AI Travel Planner")
st.warning("Демонстрационный режим. Gemini не подключён и не вызывается.")
st.caption("Ограничения текущей формы: Алматы, один путешественник, русский язык, бюджет на всю поездку в KZT. "
           "Поездка — от 1 до 3 календарных дней включительно.")
st.caption("Один путешественник и русский язык — проектные допущения контракта, которые команде ещё нужно согласовать.")
st.caption("Планируемый бюджет включает входные билеты, питание и местный транспорт; "
           "жильё и дорога до Алматы исключены. Сейчас бюджет не рассчитывается.")
st.caption("Бронирование, оплата, карта и погода не входят в текущую форму.")

interest_labels = {
    "culture": "Культура",
    "history": "История",
    "nature": "Природа",
    "food": "Еда",
    "walking": "Прогулки",
}
default_request, _ = build_demo()

with st.form("trip_form"):
    start_date = st.date_input("Дата начала", value=default_request.start_date, key="start_date")
    end_date = st.date_input("Дата окончания", value=default_request.end_date, key="end_date")
    budget_kzt = st.number_input(
        "Общий бюджет поездки, KZT", min_value=1, value=10000, step=1000, key="budget_kzt"
    )
    interests = st.multiselect(
        "Интересы",
        options=list(interest_labels),
        format_func=interest_labels.get,
        default=["walking"],
        key="interests",
    )
    submitted = st.form_submit_button("Показать демонстрационный пример", key="submit_trip")

if submitted:
    st.session_state.pop("trip_result", None)
    st.session_state.pop("test_fixture", None)
    if end_date < start_date:
        st.error("Дата окончания не может быть раньше даты начала.")
    elif (end_date - start_date).days > 2:
        st.error("Поездка должна длиться от 1 до 3 календарных дней включительно.")
    elif not interests:
        st.error("Выберите хотя бы один интерес.")
    else:
        try:
            request = TripRequest(
                schema_version=SCHEMA_VERSION,
                start_date=start_date,
                end_date=end_date,
                budget_kzt=budget_kzt,
                interests=interests,
                city="Almaty",
                currency="KZT",
                travelers=1,
                language="ru",
            )
        except ValidationError:
            st.error("Параметры не прошли проверку контракта. Проверьте даты, бюджет и интересы.")
        else:
            _, result = build_demo(request)
            st.session_state["trip_result"] = result.model_dump(mode="json")

if "trip_result" in st.session_state:
    try:
        result = TripResult.model_validate(st.session_state["trip_result"])
    except ValidationError:
        st.error("Результат не соответствует контракту TripResult и не может быть показан.")
    else:
        st.subheader(
            "Демонстрационный результат"
            if result.metadata.mode == "demo"
            else "Результат поездки"
        )
        render_trip_result(result, test_fixture=st.session_state.get("test_fixture", False))
        with st.expander("Полный результат по контракту"):
            st.json(result.model_dump(mode="json"), expanded=True)

st.caption("Ернур: каталог, AI и расписание. Рахат: интерфейс и модуль бюджета. "
           "К текущей форме реальные источники, генерация и расчёты пока не подключены.")

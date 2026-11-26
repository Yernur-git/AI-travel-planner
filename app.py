import streamlit as st
from pydantic import ValidationError

from src.demo import build_demo
from src.contracts.models import SCHEMA_VERSION, TripRequest

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
    st.session_state.pop("trip_request", None)
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
            st.session_state["trip_request"] = request.model_dump(mode="python")

if "trip_request" in st.session_state:
    request, result = build_demo(TripRequest.model_validate(st.session_state["trip_request"]))
    st.subheader("Демонстрационный результат")
    st.info(result.message)
    st.caption("Это фиксированная учебная структура: выбранные интересы не подбирают места, "
               "а введённый бюджет не рассчитывается и не проверяется.")
    st.write(
        f"Даты: {request.start_date.isoformat()} — {request.end_date.isoformat()} · "
        f"Бюджет: {request.budget_kzt:,} KZT · "
        f"Интересы: {', '.join(interest_labels[item] for item in request.interests)}"
    )
    st.write("Статус: partial — неполная проверка. Расходы неизвестны. Источников: 0.")
    for day in result.itinerary:
        st.write(f"День {day.date.isoformat()}")
        for activity in day.activities:
            st.write(f"{activity.start_time}–{activity.end_time}: {activity.place_name}")
            st.caption(activity.reason)
    st.write("Итоговая стоимость и остаток бюджета неизвестны. "
             "Известная часть 0 KZT не означает, что поездка бесплатна.")
    with st.expander("Полный результат по контракту"):
        st.json(result.model_dump(mode="json"), expanded=True)

st.caption("Ернур: каталог, AI и расписание. Рахат: интерфейс и бюджет. "
           "Реальные источники, генерация и расчёты ещё не реализованы.")

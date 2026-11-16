import streamlit as st

from src.demo import build_demo

st.set_page_config(page_title="AI Travel Planner — демонстрация", page_icon=None)
st.title("AI Travel Planner")
st.warning("Демонстрационный режим. Gemini не подключён и не вызывается.")
st.write("Общая основа проекта: пример запроса и результата для поездки по Алматы.")
st.caption("В демо один день, один человек и бюджет 10 000 KZT. "
           "Дата примера — завтра по времени Алматы; это не выбранная вами поездка.")

request, result = build_demo()
st.subheader("Демонстрационный запрос")
st.json(request.model_dump(mode="json"), expanded=True)

if st.button("Показать демонстрационный результат", key="show_demo"):
    st.session_state["demo_visible"] = True

if st.session_state.get("demo_visible", False):
    st.subheader("Демонстрационный результат")
    st.info(result.message)
    st.write("Статус: partial — неполная проверка. Расходы: неизвестны. Источников: 0.")
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

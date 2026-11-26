"""Render validated TripResult values in Streamlit."""

import streamlit as st

from src.contracts.models import Issue, Source, TripResult

STATUS_LABELS = {
    "ok": "Маршрут проверен",
    "partial": "Маршрут проверен частично",
    "infeasible": "Не удалось составить допустимый маршрут",
    "invalid_request": "Проверьте параметры запроса",
    "service_error": "Ошибка сервиса",
}
SCHEDULE_LABELS = {"valid": "проверено", "invalid": "есть нарушения", "unknown": "неизвестно"}
BUDGET_LABELS = {
    "within_budget": "в пределах бюджета",
    "over_budget": "превышает бюджет",
    "unknown": "неизвестно",
}
CATEGORY_LABELS = {"entry": "билеты", "food": "питание", "transport": "местный транспорт"}
COST_KIND_LABELS = {
    "published_price": "Опубликованная цена",
    "editorial_estimate": "Редакционная оценка",
    "unknown": "Сумма неизвестна",
}
KIND_LABELS = {"visit": "Посещение", "meal": "Приём пищи", "break": "Перерыв"}
INTEREST_LABELS = {
    "culture": "Культура",
    "history": "История",
    "nature": "Природа",
    "food": "Еда",
    "walking": "Прогулки",
}
MODE_LABELS = {"ai": "AI", "baseline": "базовый алгоритм", "demo": "демонстрационные данные"}
ZERO_KNOWN_PART_NOTE = (
    "только подтверждённая часть; это не значит, что поездка бесплатна"
)


def _money(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def _source_links(source_ids: list[str], sources: dict[str, Source]) -> None:
    for source_id in source_ids:
        source = sources.get(source_id)
        if source is not None:
            st.markdown(
                f"[{source.title}]({source.url}) — {source.publisher}; "
                f"проверено {source.checked_at.date().isoformat()}"
            )


def _issues(issues: list[Issue], activities: dict[str, str] | None = None) -> None:
    activities = activities or {}
    for issue in issues:
        target = ""
        if issue.date is not None:
            target = f" · {issue.date.isoformat()}"
        if issue.activity_id:
            name = activities.get(issue.activity_id, issue.activity_id)
            target += f" · {name}"
        st.write(f"**{issue.code}**{target}: {issue.message}")


def render_trip_result(result: TripResult, *, test_fixture: bool = False) -> None:
    """Display itinerary, provenance, budget and every contract status."""
    if test_fixture:
        st.warning("ТЕСТОВЫЙ ПРИМЕР: синтетические данные только для проверки отображения.")
        st.caption("Источник результата: синтетическая AppTest-фикстура.")
    else:
        st.caption(f"Источник результата: {MODE_LABELS[result.metadata.mode]}.")

    st.subheader(STATUS_LABELS[result.status])
    st.write(result.message)

    if result.status == "partial":
        st.warning("Маршрут проверен не полностью; неизвестные данные не считаются подтверждёнными.")
    elif result.status in {"infeasible", "invalid_request", "service_error"}:
        st.info("Маршрут не сформирован.")

    if result.warnings:
        st.markdown("#### Предупреждения")
        for warning in result.warnings:
            st.warning(f"{warning.code}: {warning.message}")

    if result.errors:
        st.markdown("#### Ошибки")
        for error in result.errors:
            details = []
            if error.field:
                details.append(f"поле: {error.field}")
            if error.activity_id:
                details.append(f"активность: {error.activity_id}")
            suffix = f" ({'; '.join(details)})" if details else ""
            st.error(f"{error.code}{suffix}: {error.message}")

    if result.request is not None:
        st.caption(
            f"Даты: {result.request.start_date.isoformat()} — "
            f"{result.request.end_date.isoformat()} · "
            f"Бюджет поездки: {_money(result.request.budget_kzt)} KZT · "
            f"Интересы: {', '.join(INTEREST_LABELS[item] for item in result.request.interests)}"
        )

    sources = {source.source_id: source for source in result.sources}
    activity_names: dict[str, str] = {}
    if result.itinerary is not None:
        st.markdown("### Маршрут по дням")
        for day in result.itinerary:
            st.markdown(f"#### День {day.date.isoformat()}")
            known_part = f"Известная часть: {_money(day.known_subtotal_kzt)} KZT"
            if day.known_subtotal_kzt == 0:
                known_part += f" — {ZERO_KNOWN_PART_NOTE}"
            st.caption(
                f"{known_part} · "
                + (
                    f"оценка дня: {_money(day.total_estimate_kzt)} KZT"
                    if day.total_estimate_kzt is not None
                    else "итог дня неизвестен"
                )
            )
            for activity in day.activities:
                name = activity.place_name or (
                    KIND_LABELS[activity.kind] if activity.kind != "visit" else "Место не указано"
                )
                activity_names[activity.activity_id] = name
                st.write(
                    f"**{activity.start_time}–{activity.end_time} · "
                    f"{KIND_LABELS[activity.kind]}: {name}**"
                )
                st.caption(activity.reason)
                _source_links(activity.source_ids, sources)

            for transfer in day.transfers:
                start = activity_names.get(transfer.from_activity_id, transfer.from_activity_id)
                end = activity_names.get(transfer.to_activity_id, transfer.to_activity_id)
                duration = (
                    f"{transfer.duration_minutes} мин"
                    if transfer.duration_minutes is not None
                    else "время неизвестно"
                )
                st.caption(f"Переход: {start} → {end} · {duration}")

    if result.schedule_check is not None:
        st.markdown("### Проверка расписания")
        st.write(f"Статус: {SCHEDULE_LABELS[result.schedule_check.status]}")
        _issues(result.schedule_check.issues, activity_names)

    if result.budget is not None:
        budget = result.budget
        st.markdown("### Расходы и бюджет")
        st.write(f"Лимит: {_money(budget.limit_kzt)} KZT")
        st.write(f"Статус бюджета: {BUDGET_LABELS[budget.budget_status]}")
        known_subtotal = f"Известная часть расходов: {_money(budget.known_subtotal_kzt)} KZT"
        if budget.known_subtotal_kzt == 0:
            known_subtotal += f" — {ZERO_KNOWN_PART_NOTE}"
        st.write(known_subtotal)
        st.write(
            "Итоговая оценка: "
            + (
                f"{_money(budget.total_estimate_kzt)} KZT"
                if budget.total_estimate_kzt is not None
                else "неизвестна"
            )
        )
        st.write(
            "Остаток бюджета: "
            + (
                f"{_money(budget.remaining_kzt)} KZT"
                if budget.remaining_kzt is not None
                else "неизвестен"
            )
        )
        with st.expander("Детализация расходов"):
            for item in budget.items:
                owner = ""
                if item.activity_id:
                    owner = f" · {activity_names.get(item.activity_id, item.activity_id)}"
                elif item.from_activity_id and item.to_activity_id:
                    start = activity_names.get(item.from_activity_id, item.from_activity_id)
                    end = activity_names.get(item.to_activity_id, item.to_activity_id)
                    owner = f" · {start} → {end}"
                amount = (
                    f"{_money(item.amount_kzt)} KZT"
                    if item.amount_kzt is not None
                    else "неизвестна"
                )
                st.write(
                    f"{item.date.isoformat()} · {CATEGORY_LABELS[item.category]}{owner}: "
                    f"{amount} · {COST_KIND_LABELS[item.kind]}"
                )
                if item.assumption:
                    st.caption(f"Основание: {item.assumption}")
                _source_links(item.source_ids, sources)
            _issues(budget.issues, activity_names)

    st.markdown("### Источники")
    if result.sources:
        _source_links(list(sources), sources)
    else:
        st.write("Источники не указаны.")

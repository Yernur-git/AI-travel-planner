# Session 02 — App foundation

Date: 2026-11-16
Participant: Bekbolat Yernur
Tool: Codex
Branch: feature/app-foundation
Task: Create and verify the shared application foundation.

## Transcript

### User
Подготовительные документы закоммичены и отправлены в main.\
Сейчас работаем в ветке feature/app-foundation.\
\
Прочитай PLAN.md, AGENTS.md, DECISIONS.md и docs/CONTRACT.md.\
\
Gemini API free tier уже выбран. Доступ и квоты пока\
не проверены. Codex используем платный. Обнови документы.\
\
Создай общую основу приложения:\
\- зависимости;\
\- .gitignore и .env.example без секретов;\
\- модели данных по CONTRACT.md;\
\- запускаемое Streamlit-приложение;\
\- явно обозначенный демонстрационный запрос и результат;\
\- README с установкой и запуском.\
\
Это подготовка к разделению работы:\
Ернур отвечает за каталог, AI и расписание;\
Рахат — за интерфейс и бюджет.\
Не реализуй полностью обе части.\
Не выдавай демонстрационный результат за ответ Gemini.\
\
Проверь запуск и модели данных. Объясни, как мне самому\
запустить приложение и проверить результат.\
Перечисли, чего ещё не хватает для checkpoint.\
\
Не делай commit, push и merge.

### Codex
Готова общая основа в feature/app-foundation: зависимости, .gitignore, пустой .env.example, [модели данных](C:/HOME-WORKS/AI/travel-planner/src/contracts/models.py), Streamlit и отдельное демо. Документы обновлены: Gemini free tier выбран, доступ и квоты не проверены; Codex платный.

Демо явно обозначено: mode=demo, model=null, attempts=0. Полные части участников не реализованы.

Проверки: 46 тестов прошли, зависимости совместимы, сервер вернул 200 OK, кнопка и раскрытие результата проверены в браузере. Тестовый сервер остановлен. Commit, push и merge не выполнялись.

Запуск из папки проекта в PowerShell:
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --browser.gatherUsageStats=false
Откройте localhost:8501, нажмите «Показать демонстрационный результат». Проверьте пометку «не ответ Gemini», статус partial, неизвестные расходы и отсутствие источников.

Тесты:
.\.venv\Scripts\python.exe -m pytest -q
Подробности — в [README](C:/HOME-WORKS/AI/travel-planner/README.md).

Для checkpoint ещё нужны:
- Ернур: проверенный каталог, доступ к Gemini, реальная генерация и проверки расписания.
- Рахат: форма пользовательского запроса, расчёт бюджета и его тесты.
- Совместно: вывод реальных источников и расходов, сквозная проверка, экспорт сессии и ссылка на рабочий commit.
Демонстрация checkpoint не закрывает.

## Manual verification

I started the app locally and clicked the demo button.
The result appeared with status partial, unknown costs
and a notice that Gemini was not connected.
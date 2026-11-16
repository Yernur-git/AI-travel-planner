# Session 01 — Project planning

Date: 2026-11-16
Participant: Bekbolat Yernur
Tool: Codex
Task: Prepare the project plan, agent instructions and data contract.

## Transcript
### User
# Подготовить план AI Travel Planner

> Мы начинаем групповой учебный проект AI Travel Planner.\
> Участники: я и Рахат. Полные требования преподавателя приложены.\
> \
> Продукт: планировщик поездок по Алматы на 1–3 дня.\
> Пользователь указывает даты, бюджет и интересы.\
> Приложение создаёт маршрут по дням с источниками\
> и оценкой расходов. Бронирования и оплаты нет.\
> Карта и погода — дополнительные цели.\
> \
> Моя часть: данные, источники, AI и оценка качества AI.\
> Часть Рахата: интерфейс, расчёт бюджета и его тесты.\
> \
> Сейчас подготовь проект до начала написания кода:\
> 1\. Выдели обязательные требования и неизвестные детали.\
> 2\. Предложи простой стек и структуру проекта на 5 недель.\
> 3\. Создай PLAN.md с этапами, задачами и ответственными.\
> 4\. Создай AGENTS.md с правилами работы агента.\
> 5\. Создай DECISIONS.md и папку agent-logs/.\
> 6\. Опиши общий формат запроса и результата:\
> &#x20;  что интерфейс передаёт AI и что получает обратно.\
> \
> В AGENTS.md укажи:\
> \- работать только в рамках текущей задачи;\
> \- не менять часть другого участника без согласования;\
> \- проверять изменения;\
> \- не сохранять секреты в Git;\
> \- не придумывать источники, результаты тестов и логи;\
> \- после задачи объяснять изменения и ручную проверку.\
> \
> Не пиши код приложения на этом этапе.\
> Не отмечай незавершённые задачи выполненными.\
> Не придумывай неизвестные даты и доступы.
>
> User context
>
> Attachments:
> - Final Project: full requirements This page replaces the written final exam (the…: `C:/Users/yernur/.codex/attachments/830098ee-26b5-490c-9587-e75f6b33ea66/Pasted text.txt`
> - Project Proposal.docx: `C:/Users/yernur/Downloads/Project Proposal.docx`

<details><summary>6 previous messages</summary>

### Codex
> Изучу требования преподавателя, предложение проекта и содержимое папки. Затем подготовлю план, правила работы и контракт обмена данными без кода приложения. Использую навыки чтения документов и проверки ясности текста.
>
> <details><summary>Ran 2 commands</summary>
>
> <details><summary>Explored a file</summary>
>
> - Read `C:/Users/yernur/.codex/skills/.system/antislop/SKILL.md`
>
> </details>
>
> - Ran `Get-ChildItem -Force; Get-Content -LiteralPath 'C:\Users\yernur\.codex\attachments\830098ee-26b5-490c-9587-e75f6b33ea66\Pasted text.txt'`
>
> <details><summary>Explored a file</summary>
>
> - Read `C:/Users/yernur/.codex/plugins/cache/openai-primary-runtime/documents/26.1112.11217/skills/documents/SKILL.md`
>
> </details>
>
> - Ran `Get-Content -LiteralPath 'C:\Users\yernur\.codex\skills\antislop\SKILL.md'; Get-Content -LiteralPath 'C:\Users\yernur\.codex\plugins\cache\openai-primary-runtime\documents\26.1112.11217\skills\documents\tasks\read_review.md'; $p = 'C:\Users\yernur\Downloads\Project Proposal.docx'; Add-Type -AssemblyName System.IO.Compression.FileSystem; $z = [IO.Compression.ZipFile]::OpenRead($p); try { $e = $z.GetEntry('word/document.xml'); $r = [IO.StreamReader]::new($e.Open()); [xml]$x = $r.ReadToEnd(); $r.Dispose(); $ns = [Xml.XmlNamespaceManager]::new($x.NameTable); $ns.AddNamespace('w','http://schemas.openxmlformats.org/wordprocessingml/2006/main'); $x.SelectNodes('//w:p',$ns) | ForEach-Object { ($_.SelectNodes('.//w:t',$ns) | ForEach-Object { $_.'#text' }) -join '' } } finally { $z.Dispose() }; Get-Item .; git status --short; rg --files -g AGENTS.md -g '!node_modules' -g '!vendor' C:\HOME-WORKS\AI`
>
> </details>
>
> В предложении уже описаны Python + Streamlit, каталог примерно из 25 мест и оценка AI на 10 фиксированных запросах. Возьму это за основу, а доступ к Gemini API и его лимиты оставлю неподтверждёнными.
>
> По требованиям checkpoint назначен на сегодня, 16 ноября 2026: к нему нужна работающая версия от формы до результата. Подготовка документов сама по себе этот этап не закрывает. Отмечу это в плане отдельно и сохраню официальный срок заморозки — 13 декабря.
>
> <details><summary>Created 5 files, ran a command, searched the web</summary>
>
> Searched the web for `site.docs.streamlit.io get started installation streamlit ...`
>
> - Ran `Get-ChildItem -Force -LiteralPath 'C:\HOME-WORKS\AI\travel-planner'; foreach ($p in @('C:\AGENTS.md','C:\HOME-WORKS\AGENTS.md','C:\HOME-WORKS\AI\AGENTS.md','C:\HOME-WORKS\AI\travel-planner\AGENTS.md')) { if (Test-Path -LiteralPath $p) { Write-Output $p; Get-Content -LiteralPath $p } }`
>
> - Wrote `./AGENTS.md` (+42 -0)
> - Wrote `./DECISIONS.md` (+64 -0)
> - Wrote `./PLAN.md` (+198 -0)
> - Wrote `./agent-logs/001-planning-summary.md` (+22 -0)
> - Wrote `./agent-logs/README.md` (+9 -0)
>
> </details>
>
> План и правила работы созданы. В контракте разделю задачи так: AI выбирает места и предлагает расписание, модуль Рахата считает расходы, а приложение подставляет проверенные источники из каталога. Неизвестные цены и часы будут явно обозначаться, чтобы результат не выглядел точнее, чем позволяют данные.
>
> Все будущие задачи оставлены открытыми. Также добавлено резюме этой реальной сессии с пометкой, что это не полный экспорт чата.
>
> <details><summary>Created a file, edited a file, ran 2 commands</summary>
>
> - Wrote `./docs/CONTRACT.md` (+163 -0)
> - Ran ````$expected = @('PLAN.md','AGENTS.md','DECISIONS.md','docs/CONTRACT.md','agent-logs/README.md','agent-logs/001-planning-summary.md'); foreach ($file in $expected) { $item = Get-Item -LiteralPath $file -ErrorAction Stop; $content = Get-Content -LiteralPath $file -Raw; if ([string]::IsNullOrWhiteSpace($content)) { throw "Empty document: $file" }; $fences = ([regex]::Matches($content, '(?m)^```')).Count; if (($fences % 2) -ne 0) { throw "Unbalanced Markdown fences: $file" }; Write-Output "$file : $($item.Length) bytes; Markdown fences balanced" }; $files = @(Get-ChildItem -Recurse -Force -File); $unexpected = @($files | Where-Object { $_.Extension -ne '.md' }); if ($unexpected.Count -gt 0) { throw 'Unexpected non-Markdown files' }; $done = Select-String -Path $expected -Pattern '^\s*-\s+\[[xX]\]'; if ($done) { throw 'Completed checkboxes found' }; Write-Output 'Only the six intended Markdown documents exist; no completed task checkboxes.'; $references = @('PLAN.md','AGENTS.md','DECISIONS.md','docs/CONTRACT.md','agent-logs/'); foreach ($reference in $references) { if (-not (Test-Path -LiteralPath $reference)) { throw "Missing reference: $reference" } }; Write-Output 'Current project document references exist. Proposed implementation paths remain future work.'; $secretPatterns = '(?i)(AIza[0-9A-Za-z_-]{30,}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN .*PRIVATE KEY-----)'; $secrets = Select-String -Path $expected -Pattern $secretPatterns; if ($secrets) { throw 'Potential secret pattern found; inspect without printing content' }; Write-Output 'No common API-token/private-key patterns found in generated documents (limited pattern check).'; Get-ChildItem -Recurse -File | Select-Object FullName,Length````
> - Wrote `./agent-logs/001-planning-summary.md` (+7 -1)
> - Ran `$files = @(Get-ChildItem -Recurse -File); if ($files.Count -ne 6 -or @($files | Where-Object { $_.Extension -ne '.md' }).Count -gt 0) { throw 'Unexpected final file set' }; if (Select-String -Path $files.FullName -Pattern '^\s*-\s+\[[xX]\]') { throw 'Completed task checkbox found' }; Get-Content -LiteralPath 'agent-logs/001-planning-summary.md' -Tail 12; Write-Output 'Final document set checked after log update.'`
>
> </details>
</details>

Подготовил документы без кода приложения:

- [PLAN.md](./PLAN.md) — требования, неизвестные детали, стек и пять этапов с ответственными.
- [AGENTS.md](./AGENTS.md) — все запрошенные правила работы агента.
- [DECISIONS.md](./DECISIONS.md) — решения, предложения и неподтверждённые допущения.
- [Контракт обмена](./docs/CONTRACT.md) — вход формы, черновик AI, проверки и результат для интерфейса.
- [agent-logs](./agent-logs/README.md) — правила сохранения сессий и честное резюме текущей работы.

Предложен Python + Streamlit, JSON-каталог и Gemini API как кандидат без подтверждённого доступа.

**Срочный момент:** checkpoint по требованиям — сегодня, **16 ноября 2026**. Он требует работающую сквозную версию; документы его не закрывают. Freeze — **13 декабря**.

Проверены наличие и структура файлов, ссылки на созданные документы и отсутствие закрытых будущих задач. Тесты приложения не запускались: кода нет. Для ручной проверки начните с неизвестных деталей в PLAN и согласуйте контракт с Рахатом.

# engineering-standards

Общие правила разработки для любого проекта и любого агента (Claude Code,
GigaCode CLI, другие с поддержкой `SKILL.md` и `AGENTS.md`):

- **бэкенд** на Python — архитектура, HTTP API, безопасность, нагрузка,
  надёжность, наблюдаемость, миграции;
- **фронтенд** на TypeScript и React — стек, структура по фичам, состояние,
  работа с API, формы, безопасность, скорость, доступность, тесты.

## Состав

| Что | Где | Когда загружается |
|---|---|---|
| Общее ядро: уровни правил, отклонения, когда звать скиллы | `core.md` | в каждой сессии |
| Ядро бэкенда / фронтенда (~140 строк каждое) | `backend.md`, `frontend.md` | в каждой сессии, если область выбрана (`--profile`) |
| Каталоги правил с номерами | `skills/backend-guide/catalog.md`, `skills/frontend-guide/catalog.md` | по требованию |
| Руководства: шаблоны, API, безопасность, скорость, тесты, перенос старого кода | `skills/backend-guide/`, `skills/frontend-guide/` | скиллы `*-guide` |
| Ревью фичи или репозитория + скрипт проверок | `skills/backend-review/` (`arch_check.py`), `skills/frontend-review/` (`fe_check.py`) | скиллы `*-review` |
| Правила по путям (только Claude Code) | `adapters/claude/rules/` | при работе с файлами слоя |
| Шаблоны проекта | `templates/` (`AGENTS.md`, `.importlinter`, `pyproject.toml`), `templates/frontend/` (ESLint, tsconfig, openapi-ts, knip) | вручную или `install.sh project` |

## Установка

```bash
./install.sh claude                          # дома: ~/.claude (или $CLAUDE_CONFIG_DIR), обе области
./install.sh gigacode --profile backend      # на работе, только бэкенд
./install.sh project ../my-svc --tool gigacode --profile backend,frontend   # в репозиторий проекта, для команды
./install.sh claude --dry-run                # посмотреть, что будет сделано
```

В глобальных инструкциях появляется блок между метками
`<!-- engineering-standards:begin/end -->` с импортом `core.md` и ядер
выбранных областей; личное вне блока не трогается. Чужой прежний файл
сохраняется как `*.bak-<дата>`. Скиллы и правила — симлинками, правка в
репозитории сразу действует везде; повторный запуск с другим `--profile`
убирает лишнее. В проект — копиями, ядра встраиваются блоком в `AGENTS.md`.

Обе области — около 320 строк в каждой сессии. Если фронтенд не пишется,
ставить `--profile backend`.

## Как пользоваться

- Новый проект / домен / фича — агент сам зовёт `backend-guide` или
  `frontend-guide` (так сказано в ядре); можно явно: `/frontend-guide`.
- После фичи: `/backend-review`, `/frontend-review` (изменения ветки) или с аргументом `repo`.
- Скрипты отдельно:
  - `uv run python skills/backend-review/scripts/arch_check.py --repo <проект> [--diff develop] [--legacy app.old]`
  - `python3 skills/frontend-review/scripts/fe_check.py --repo <фронтенд> [--diff main] [--legacy src/legacy]`
- Отступление от правила — строка в `AGENTS.md`, раздел «Отклонения от общих правил»:
  `- TX-02: <где и почему>`. В коде — `# arch-ignore[TX-02]: причина` / `// arch-ignore[FSEC-01]: причина`.

Скрипты — эвристики без зависимостей (только стандартная библиотека Python):
находят механическое (границы, токены в хранилище, секреты, `any`, пустые
`catch`, раскладку), что модель легко пропускает на большом диффе и что
линтер проекта может не проверять. Каждую находку ревью проверяет глазами.

## Как менять правила

1. Правило — в каталог своей области (номер, уровень, почему, проверка, исключение).
2. Если оно главное — одна строка в `backend.md` / `frontend.md`; общее для обеих — в `core.md`.
3. Если проверяется механически — проверка в скрипте ревью, уровень в `SEVERITY`.
4. Если касается слоя — строка в `adapters/claude/rules/<область>-<слой>.md` и в чек-листе ревью.
5. Прогнать скрипт на реальном проекте: новых ложных срабатываний быть не должно.

## Источники

**Бэкенд.** Архитектура: Fowler (домены сверху, слои внутри), «Architecture
Patterns with Python» (Cosmic Python), Kraken (import-linter на большом
монолите), Vernon (агрегаты). API: RFC 9457, Google AIP-158, Zalando RESTful
API Guidelines, IETF draft Idempotency-Key. Безопасность: OWASP API Security
Top 10 (2023), OWASP Logging Cheat Sheet / ASVS V7. Надёжность: AWS Builders'
Library (таймауты, повторы, джиттер), Google SRE (золотые сигналы), RED/USE.
Миграции: GoCardless, postgres.ai (lock_timeout, expand/contract).

**Фронтенд.** react.dev (создание проекта, «You Might Not Need an Effect»,
React Compiler 1.0), документация Vite 8, TanStack Router/Query, hey-api,
shadcn/ui, Vitest 4, Playwright; bulletproof-react и Feature-Sliced Design
(структура); web.dev (Core Web Vitals); WCAG 2.2; OWASP Cheat Sheets (XSS,
HTML5, CSP), IETF «OAuth 2.0 for Browser-Based Applications» (BFF, хранение
токенов).

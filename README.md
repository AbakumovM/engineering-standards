# engineering-standards

Общие правила Python-бэкенда — архитектура, HTTP API, безопасность, нагрузка,
надёжность, наблюдаемость, миграции —: для любого проекта и любого
агента (Claude Code, GigaCode CLI, другие с поддержкой `SKILL.md` и `AGENTS.md`).

## Состав

| Что | Где | Когда загружается |
|---|---|---|
| Ядро (~150 строк) | `core.md` | в каждой сессии — через импорт из глобальных инструкций |
| Каталог правил с номерами | `skills/backend-guide/catalog.md` | по требованию |
| Руководство: шаблон домена, транзакции, API, безопасность, нагрузка, надёжность, логи, эксплуатация, перенос легаси, стеки | `skills/backend-guide/` | скилл `backend-guide` |
| Ревью фичи или репозитория + скрипт проверок | `skills/backend-review/` | скилл `backend-review` |
| Правила по слоям (только Claude Code) | `adapters/claude/rules/` | при работе с файлами слоя |
| Шаблоны проекта | `templates/` | `AGENTS.md`, `.importlinter`, `pyproject.toml` |

## Установка

```bash
./install.sh claude              # дома: ~/.claude (или $CLAUDE_CONFIG_DIR)
./install.sh gigacode            # на работе: ~/.gigacode
./install.sh project ../my-svc --tool gigacode   # в репозиторий проекта, для команды
./install.sh claude --dry-run    # посмотреть, что будет сделано
```

Глобальные инструкции заменяются шаблоном с импортом `core.md`; прежний файл
сохраняется рядом как `*.bak-<дата>`. Скиллы и правила — симлинками, поэтому
правка в репозитории сразу действует везде. В проект — копиями (повторный
запуск обновляет их и блок общих правил в `AGENTS.md`).

## Как пользоваться

- Новый проект / домен / сценарий — агент сам зовёт `backend-guide`
  (так сказано в ядре); можно явно: `/backend-guide`.
- После фичи: `/backend-review` (изменения ветки) или `/backend-review repo`.
- Скрипт отдельно: `uv run python skills/backend-review/scripts/arch_check.py --repo <проект> [--diff develop] [--legacy app.old]`.
- Отступление от правила в проекте — строка в `AGENTS.md`, раздел «Отклонения от общих правил»:
  `- TX-02: <где и почему>`. В коде — `# arch-ignore[TX-02]: причина`.

## Как менять правила

1. Правило — в `catalog.md` (номер, уровень, почему, проверка, исключение).
2. Если оно главное — одна строка в `core.md` (держать около 150 строк).
3. Если проверяется механически — проверка в `arch_check.py`, уровень в `SEVERITY`.
4. Если касается слоя — строка в `adapters/claude/rules/backend-<слой>.md` и в чек-листе ревью.
5. Прогнать скрипт на реальном проекте: новых ложных срабатываний быть не должно.

## Источники

Архитектура: Fowler (домены сверху, слои внутри), «Architecture Patterns with
Python» (Cosmic Python), Kraken (import-linter на большом монолите), Vernon
(агрегаты). API: RFC 9457, Google AIP-158, Zalando RESTful API Guidelines,
IETF draft Idempotency-Key. Безопасность: OWASP API Security Top 10 (2023),
OWASP Logging Cheat Sheet / ASVS V7. Надёжность: AWS Builders' Library
(таймауты, повторы, джиттер), Google SRE (золотые сигналы), RED/USE.
Миграции: GoCardless, postgres.ai (lock_timeout, expand/contract).

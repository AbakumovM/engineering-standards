# Новый проект

## Раскладка

```
<repo>/
  src/<пакет>/
    <домен>/                 # по шаблону domain-template.md
    infrastructure/
      config.py              # Settings (pydantic-settings), из .env
      db.py                  # engine/пул с таймаутами (ADP-01)
      uow.py                 # единица работы: сессия на запрос, commit/rollback
      ioc.py                 # make_container(*providers)
      http.py                # общий httpx-клиент с таймаутами
    api_main.py              # FastAPI: контейнер, роутеры доменов, /health/live, /health/ready (REL-04)
    worker_main.py           # брокер / фоновые задачи — когда появятся
  migrations/                # Alembic (DB-02)
  tests/
  .importlinter              # из templates/importlinter.ini
  pyproject.toml             # ruff, mypy strict, pytest — из templates/pyproject.toml
  AGENTS.md                  # из templates/AGENTS.md
  docker-compose.test.yml    # тестовая БД
```

## Первые шаги

1. `uv init`, зависимости стека, `templates/pyproject.toml`.
2. Инфраструктура: Settings с проверкой при старте (OPS-03), БД с таймаутами
   и `statement_timeout` (PERF-04), UoW, контейнер, health (REL-04), lifespan с
   мягкой остановкой (REL-05), структурированные логи с `request_id` (OBS-01, OBS-02),
   единый формат ошибок (API-02).
3. `AGENTS.md` проекта по шаблону: что за сервис, команды, «Отклонения».
4. `.importlinter` с контрактами слоёв; проверить пробным нарушением.
5. Первый домен — по `domain-template.md`, с тестами всех четырёх видов.
6. CI: `ruff`, `lint-imports`, `mypy`, `pytest` на каждый push.

## Чего не делать в начале

- Микросервисы, брокер, кэш «на будущее» (STR-06). Появляется задача,
  которую не тянет БД, — тогда адаптер в `infrastructure/`.
- Пустые слои-заготовки (`services/`, `events.py`, `v1/`) (STR-03).
- Общий `Settings` во все сценарии: сценарий получает `{Что}Config` (DEP-03).

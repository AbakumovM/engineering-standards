# <Название сервиса>

<Одна-две фразы: что делает сервис, для кого.>

Общие правила — глобальные инструкции и скиллы `backend-guide`/`backend-review`
(бэкенд), `frontend-guide`/`frontend-review` (фронтенд). Здесь — только то,
что относится к этому проекту.

## Состав

| Процесс | Точка входа | Что делает |
|---|---|---|
| API | `src/app/api_main.py` | ... |

Домены: `assets` (образец структуры), ...

## Команды

```bash
uv sync
docker compose -f docker-compose.test.yml up -d --wait   # тестовая БД
uv run ruff check . && uv run lint-imports && uv run mypy && uv run pytest
uv run alembic upgrade head
# фронтенд (если есть), из web/:
pnpm install && pnpm api:generate && pnpm lint && pnpm typecheck && pnpm test
```

## Отклонения от общих правил

<!-- Одна строка на отклонение: номер правила, где, почему. Записанное — не нарушение. -->
- DB-01: ...
- FSTR-04: ...

## Что важно знать

<!-- То, что нельзя вывести из кода: внешние системы, инварианты, решения владельца. -->

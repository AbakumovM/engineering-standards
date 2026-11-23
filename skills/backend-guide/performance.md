# Нагрузка

Правила — `catalog.md`, группа PERF.

## Перед тем как оптимизировать

1. Измерить: какой эндпоинт, какой запрос, сколько времени (метрики OBS-05,
   `pg_stat_statements`, `EXPLAIN (ANALYZE, BUFFERS)`).
2. Чинить самое дорогое. Кэш (PERF-07) — последним, не первым.

## Запросы (PERF-01, PERF-02, PERF-08)

| Признак | Исправление |
|---|---|
| `await` запроса внутри `for` | один запрос с `IN`/JOIN, `selectinload` |
| `SELECT *` и фильтр в Python | фильтр и агрегат в SQL (ADP-04) |
| `OFFSET` на большой таблице | keyset по индексу (API-04) |
| `Seq Scan` по растущей таблице в `EXPLAIN` | индекс под `WHERE` + `ORDER BY` |
| `COUNT(*)` на каждой странице | `limit + 1` или отдельный эндпоинт |
| Вставка/обновление по строке | batch: `executemany`, `insert().values([...])`, `UPDATE ... FROM (VALUES ...)` |
| Обход всей таблицы одним запросом | пачки по 500–5000 keyset-ом |

Составной индекс: сначала колонки равенства, затем сортировки/диапазона
(`(owner_id, created_at DESC, id DESC)`).

## Соединения (PERF-03, PERF-04)

```
экземпляры × процессы × (pool_size + max_overflow) + фоновые + миграции ≤ max_connections − резерв
пример: 2 × 4 × (5 + 5) + 10 + 2 = 92 ≤ 100 − 5
```

- Пул на процесс небольшой (5–10): больше соединений — не быстрее, Postgres
  на каждое тратит память и CPU.
- Много экземпляров или serverless — PgBouncer, режим transaction (у asyncpg
  тогда `statement_cache_size=0`).
- Роль приложения:
  ```sql
  ALTER ROLE app SET statement_timeout = '5s';
  ALTER ROLE app SET idle_in_transaction_session_timeout = '30s';
  ```
  Отчёты — своей ролью/явным `SET LOCAL statement_timeout` в транзакции.

## Параллельность и обратное давление (PERF-05)

```python
class PanelClient:
    def __init__(self, http: httpx.AsyncClient, max_parallel: int = 10) -> None:
        self._http = http
        self._slots = asyncio.Semaphore(max_parallel)

    async def get_user(self, uid: str) -> PanelUser:
        async with self._slots:
            ...
```

- Массовые вызовы — пачками или через семафор, не `gather(*[f(x) for x in всё])`.
- Очередь в памяти — `asyncio.Queue(maxsize=N)`; переполнена — отказ, а не рост.
- Перегрузка на входе — `429`/`503` с `Retry-After`, а не очередь из тысяч ждущих.

## Долгая работа (PERF-06)

| Работа | Где |
|---|---|
| < 1–2 с, без повторов | в запросе |
| Неважная, можно потерять (метрика, кэш-прогрев) | `BackgroundTasks` |
| Важная, долгая, с повторами (письмо, выгрузка, вызов партнёра) | очередь / таблица задач + воркер; запрос отвечает `202` + id |
| Последствие записи для других процессов | outbox (TX-09) |

Таблица задач на Postgres (`SELECT ... FOR UPDATE SKIP LOCKED LIMIT n`) —
нормальный выбор до появления реальной нужды в брокере.

## Кэш (PERF-07)

Перед кэшем ответить: что кэшируем, кто и когда инвалидирует, TTL, что
будет при недоступности кэша, что будет при одновременном промахе многих
запросов (stampede — блокировка или «один считает, остальные ждут»).

# Надёжность

Правила — `catalog.md`, группа REL.

## Таймауты (ADP-01, REL-01)

У каждого внешнего вызова — таймаут соединения и чтения; у запроса — общий
бюджет. Порядок величин:

```
балансировщик/клиент 30 с  >  запрос сервиса 10–20 с  >  каждый внешний вызов 2–5 с  >  запрос к БД 5 с
```

```python
http = httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0),
                         limits=httpx.Limits(max_connections=50, max_keepalive_connections=20))
```

## Повторы (REL-02)

```python
RETRYABLE = {429, 502, 503, 504}

async def call_with_retry(fn, *, attempts: int = 3, base: float = 0.2, cap: float = 5.0):
    for attempt in range(attempts):
        try:
            return await fn()
        except (httpx.TransportError, RetryableStatus) as exc:
            if attempt == attempts - 1:
                raise
            delay = getattr(exc, "retry_after", None) or random.uniform(0, min(cap, base * 2 ** attempt))
            await asyncio.sleep(delay)                          # полный джиттер
```

- Повторяем только идемпотентное (или с `Idempotency-Key`).
- Один уровень повторов: если повторяет клиент внешнего API, сценарий и
  контроллер не повторяют.
- `4xx` (кроме `429`) не повторяем никогда.
- Под длительным отказом — меньше повторов, не больше: бюджет или
  размыкатель (REL-03).

## Деградация (REL-03)

| Зависимость | При отказе |
|---|---|
| Обязательная (БД, платёжка при оплате) | быстрый `503` + `Retry-After` |
| Необязательная (уведомление, аналитика, рекомендации) | пропуск/фолбэк + `WARNING` в лог; дослать позже (outbox/дожим) |
| Часто падающая | размыкатель: после N ошибок — не вызывать T секунд, сразу фолбэк |

## Health (REL-04)

```python
@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}                                  # без зависимостей

@router.get("/health/ready")
async def ready(pool: FromDishka[Pool]) -> Response:
    try:
        async with asyncio.timeout(1):
            await pool.fetchval("SELECT 1")
    except Exception:
        return JSONResponse({"status": "db unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})
```

Оркестратор: liveness → `/health/live`, readiness → `/health/ready`.
Только внешний watchdog — `/health` = readiness.

## Мягкая остановка (REL-05)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    container = make_container(...)
    stop = asyncio.Event()
    loops = [asyncio.create_task(rollover_loop(container, stop))]
    yield                                                    # здесь сервер обслуживает запросы
    stop.set()                                               # сервер уже дождался текущих запросов
    await asyncio.wait(loops, timeout=10)
    await container.close()                                  # пулы, http-клиенты
```

`uvicorn --timeout-graceful-shutdown 25` — меньше grace period оркестратора (30 с).

## Фоновые циклы (REL-06)

```python
async def rollover_loop(container: AsyncContainer, stop: asyncio.Event, every: float = 60) -> None:
    while not stop.is_set():
        try:
            async with container() as request:               # область REQUEST на итерацию
                await (await request.get(RolloverInteractor)).run()
        except Exception:
            logger.exception("rollover iteration failed")    # итерация упала — цикл жив (OBS-04)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), every + random.uniform(0, every * 0.1))
```

Несколько экземпляров — внутри итерации `pg_try_advisory_xact_lock(<id задачи>)`:
не получил — пропустить итерацию.

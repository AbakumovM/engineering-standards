# Наблюдаемость

Правила — `catalog.md`, группа OBS. Вопрос, на который отвечает
наблюдаемость: «что сломалось и почему» — без чтения кода и без ssh.

## Логи (OBS-01, OBS-02, OBS-03)

```python
# infrastructure/logging.py
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

structlog.configure(processors=[
    structlog.contextvars.merge_contextvars,
    add_otel_trace_ids,                                      # trace_id/span_id текущего спана, если есть
    redact_sensitive,                                        # password/token/secret/authorization → "***"
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.dict_tracebacks,
    structlog.processors.JSONRenderer(),
])
```

- Middleware ставит `request_id` (из входящего `X-Request-ID` или новый),
  отдаёт его в ответе и кладёт в `structlog.contextvars.bind_contextvars`.
- В вызовы наружу — заголовок `X-Request-ID`/`traceparent`; в сообщения
  брокера и задачи — поле `request_id`.
- Событие — имя и поля: `logger.info("order.fulfilled", order_id=..., days=...)`,
  не `f"Order {id} fulfilled"`.

| Уровень | Когда |
|---|---|
| ERROR | нужен человек: деньги не выданы, данные расходятся, необработанное исключение |
| WARNING | деградация, которая пройдёт сама: зависимость недоступна, повтор |
| INFO | бизнес-события, старт/остановка, итог фоновой задачи |
| DEBUG | разработка; в проде выключен |

**Не логировать:** пароли, токены, ключи, `Authorization`, cookie, номера
карт, полные тела запросов/ответов, персональные данные сверх нужного для
расследования. Логировать: вход/выход/неудачный вход (без учётных данных),
изменения прав, денежные операции (id, сумма, итог).

## Исключения (OBS-04)

```python
# плохо: глотаем
try: await notify(user)
except Exception: pass

# плохо: логируем на каждом уровне
except PanelError: logger.exception("panel"); raise

# хорошо: необязательный шаг — WARNING с причиной; граница — один logger.exception
except PanelError as exc:
    logger.warning("notify.skipped", user_id=user.id, error=str(exc))
```

## Метрики (OBS-05)

| Что | Метрики |
|---|---|
| HTTP-эндпоинт, обработчик сообщения | `requests_total{route,method,status}`, `request_duration_seconds{route}` (гистограмма) |
| Внешняя зависимость | `external_calls_total{service,operation,outcome}`, `external_call_duration_seconds{service}` |
| Насыщение | занятость пула БД, длина очередей, возраст старейшей неисполненной задачи |
| Бизнес | оплаты, выдачи, ошибки выдачи — счётчиками |

Метка `route` — шаблон (`/assets/{id}`), не путь с id: иначе кардинальность взрывается.

## Алерты (OBS-06)

- По симптомам: доля 5xx > X% за 5 мин; p95 > Y; оплачено, но не выдано > N мин;
  расхождение с внешней системой > M мин; readiness падает.
- У каждого — действие (ссылка на runbook) и ограничение повтора.
- Алерт, на который никто не реагирует, удаляется или чинится.

## Трассировка (OBS-07)

OpenTelemetry: автоинструментирование FastAPI, httpx, драйвера БД; экспорт
OTLP. Спаны своих шагов — только для долгих операций сценария. `trace_id` —
в логах, чтобы из записи лога открыть трассу.

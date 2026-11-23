# HTTP API: как писать

Правила — `catalog.md`, группа API. Здесь — как это выглядит в FastAPI.

## Схемы (API-01, API-07)

```python
# controllers/schemas.py
class CreateAssetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")          # лишние поля → 422
    name: str = Field(min_length=1, max_length=200)
    tags: list[Annotated[str, Field(max_length=50)]] = Field(default_factory=list, max_length=20)


class AssetResponse(BaseModel):
    id: UUID
    name: str
    created_at: AwareDatetime

    @classmethod
    def from_info(cls, info: AssetInfo) -> "AssetResponse":
        return cls(id=info.id, name=info.name, created_at=info.created_at)
```

- Ответ строится явно из `Info`, а не `response_model=` над ORM-строкой.
- Поля, которые клиент менять не вправе (`owner_id`, `role`, `status`), в схеме команды отсутствуют.
- Потолок размера тела — на прокси/сервере (например, `client_max_body_size`) и в схеме.

## Ошибки (API-02, API-03)

```python
# infrastructure/http/errors.py — регистрируется в точке сборки
PROBLEM = "application/problem+json"

def problem(status: int, title: str, detail: str | None, request: Request) -> JSONResponse:
    body = {"type": "about:blank", "title": title, "status": status,
            "detail": detail, "request_id": request.state.request_id}
    return JSONResponse(body, status_code=status, media_type=PROBLEM)

def install_error_handlers(app: FastAPI, mapping: dict[type[Exception], tuple[int, str]]) -> None:
    for exc_type, (status, title) in mapping.items():
        app.add_exception_handler(exc_type, lambda r, e, s=status, t=title: problem(s, t, str(e), r))
    app.add_exception_handler(RequestValidationError, lambda r, e: problem(422, "Invalid request", None, r))
    app.add_exception_handler(Exception, lambda r, e: problem(500, "Internal error", None, r))  # без деталей
```

Каждый домен отдаёт свою таблицу `исключение → (код, заголовок)` из
`controllers/`; точка сборки объединяет их.

| Ситуация | Код |
|---|---|
| Тело не разобралось / не та схема | 400 / 422 |
| Нет или неверный токен | 401 |
| Нет прав на функцию | 403 |
| Нет объекта или нет прав его видеть | 404 |
| Конфликт состояния (уже оплачен, версия устарела) | 409 |
| Правило домена не пускает | 422 (или 409 — единообразно в сервисе) |
| Лимит частоты | 429 + `Retry-After` |
| Зависимость недоступна | 503 + `Retry-After` |

## Пагинация (API-04)

```python
class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None           # None — страниц больше нет

@router.get("")
async def list_assets(
    view: FromDishka[AssetView], subject: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> Page[AssetResponse]:
    after = decode_cursor(cursor)                      # (created_at, id) или None; подпись/версия внутри
    infos = await view.list(owner_id=subject.id, after=after, limit=limit + 1)
    ...
```

```sql
-- keyset: индекс (owner_id, created_at DESC, id DESC)
SELECT ... FROM assets
WHERE owner_id = $1 AND (created_at, id) < ($2, $3)
ORDER BY created_at DESC, id DESC
LIMIT $4
```

Запрос `limit + 1` строк показывает, есть ли следующая страница, без `COUNT(*)`.
Общее число — отдельным эндпоинтом и только если правда нужно.

## Идемпотентность (API-05)

```
Idempotency-Key: 8e03978e-40d5-43e8-bc93-6894a57f9324
```

```
idempotency_keys(key, subject_id, request_hash, status, response_code, response_body, created_at)
PRIMARY KEY (subject_id, key)
```

1. В транзакции: `INSERT ... ON CONFLICT DO NOTHING`; конфликт →
   - `request_hash` другой → `422`;
   - запись завершена → вернуть сохранённый ответ;
   - в работе → `409` (клиент повторит позже).
2. Выполнить сценарий; сохранить ответ в ту же запись.
3. Удалять ключи старше срока (сутки) фоновой задачей.

Стандарт — черновик IETF `draft-ietf-httpapi-idempotency-key-header` (пока не RFC).

## Совместимость (API-06)

| Изменение | Совместимо? |
|---|---|
| Новое поле в ответе | да |
| Новое необязательное поле запроса | да |
| Новый эндпоинт, новый необязательный параметр | да |
| Новое значение enum в ответе | только если клиенты готовы к неизвестным |
| Удалить/переименовать поле | нет |
| Сменить тип, формат, единицы | нет |
| Сделать поле обязательным | нет |
| Добавить пагинацию к существующему списку | нет — поэтому с первого дня |

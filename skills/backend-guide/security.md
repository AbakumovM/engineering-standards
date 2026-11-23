# Безопасность сервиса

Правила — `catalog.md`, группа SEC. Основа — OWASP API Security Top 10 (2023):

| OWASP | Риск | Правило |
|---|---|---|
| API1 | Доступ к чужому объекту по id (BOLA) | SEC-01 |
| API2 | Слабая аутентификация | SEC-03 |
| API3 | Лишние поля в ответе, mass assignment | API-01 |
| API4 | Неограниченное потребление ресурсов | API-04, API-07, PERF-05, SEC-09 |
| API5 | Доступ к функции без прав (BFLA) | SEC-02 |
| API6 | Автоматизация бизнес-процессов | SEC-09 |
| API7 | SSRF | SEC-07 |
| API8 | Небезопасные настройки | SEC-10, OPS-03 |
| API9 | Забытые эндпоинты и версии | API-08 |
| API10 | Доверие к чужим API | SEC-08 |

## Доступ к объекту (SEC-01)

Субъект — параметр сценария, правило — в домене, фильтр — в запросе:

```python
# domain/access.py
def can_view(asset: AssetAccess, subject: Subject) -> bool:
    return subject.is_admin or asset.owner_id == subject.id

# application/interactor.py
async def rename(self, subject: Subject, asset_id: UUID, name: str) -> RenameResult:
    asset = await self._gateway.get_for_update(asset_id, owner_id=subject.id)
    if asset is None:
        raise AssetNotFoundError(asset_id)          # → 404, существование не раскрываем
```

View тоже принимает субъекта/арендатора: `view.get(asset_id, owner_id=...)`.
Метод «по id» без субъекта — только для внутренних сценариев и с именем,
которое это говорит (`get_internal`).

## Доступ к функции (SEC-02)

```python
admin_router = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin"))])
```

Проверка роли — на весь роутер. Новый админский маршрут без этой зависимости
не появится случайно.

## Вебхуки (SEC-06)

```python
raw = await request.body()                                   # подпись — по сырому телу
expected = hmac.new(secret, raw, hashlib.sha256).hexdigest()
if not hmac.compare_digest(expected, request.headers.get("X-Signature", "")):
    raise HTTPException(401)
if abs(now - int(request.headers["X-Timestamp"])) > 300:     # окно от повтора
    raise HTTPException(401)
# дальше — идемпотентная обработка по id события (TX-10)
```

Провайдер без подписи — сверка статуса у провайдера по API перед действием.

## SSRF (SEC-07)

- Схема только `https`; хост — из белого списка или проверка, что разрешённый
  IP не приватный/служебный (`ipaddress.ip_address(ip).is_global`).
- `follow_redirects=False`, таймаут, потолок размера ответа (читать потоком).

## Секреты (SEC-04)

```python
class PaymentSettings(BaseSettings):
    api_key: SecretStr                                       # без значения по умолчанию
```

В логах и `repr` `SecretStr` не раскрывается; `.get_secret_value()` — только
в адаптере в момент вызова.

## Чек-лист перед выкаткой нового эндпоинта

- [ ] Кто может вызвать? Политика доступа на роутере (SEC-02).
- [ ] Чей объект? Фильтр по субъекту в запросе (SEC-01).
- [ ] Какие поля принимаем и отдаём? Явные схемы, `extra="forbid"` (API-01).
- [ ] Потолки входа и `limit` (API-04, API-07).
- [ ] Можно ли злоупотребить частотой? Лимит (SEC-09).
- [ ] Ходит ли наружу по адресу из ввода? (SEC-07)
- [ ] Что попадёт в лог? (OBS-03)

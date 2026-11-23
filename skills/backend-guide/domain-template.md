# Шаблон домена

Пример — домен `assets`, пакет `app`. Код — скелет, не копировать имена бездумно.

## Файлы

```
app/assets/
  public.py                 # для соседей: View-протоколы, Info, порты для чужой транзакции
  domain/
    models.py               # сущности и правила: без внешних зависимостей (DEP-02)
    exceptions.py           # AssetNotFoundError, …
    events.py               # только когда появилось первое событие (STR-03)
  application/
    dto.py                  # AssetInfo, MergePlan — frozen dataclass (APP-02)
    config.py               # AssetConfig — настройки значением (DEP-03)
    interfaces/
      gateway.py            # AssetGateway (запись), Transaction (commit/rollback)
      view.py               # AssetView (чтение), порты чтения соседей
      <сервис>.py           # порт внешнего сервиса (APP-06)
    interactor.py           # AssetInteractor
    <сценарий>.py           # Service, если пишет несколько доменов (APP-04)
  adapters/
    gateway.py              # SqlAssetGateway
    view.py                 # SqlAssetView
    <сервис>.py             # адаптер внешнего сервиса
  controllers/
    http.py                 # APIRouter
    <вход>.py               # bot.py, broker.py, cli.py — по мере появления
  ioc.py                    # AssetsAdaptersProvider, AssetsInteractorsProvider, assets_providers()
```

## domain/

```python
# domain/models.py
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RenameRefusal(StrEnum):
    ARCHIVED = "archived"
    SAME_NAME = "same_name"


@dataclass
class Asset:
    id: int
    name: str
    archived_at: datetime | None

    def rename_refusal(self, new_name: str) -> RenameRefusal | None:
        if self.archived_at is not None:
            return RenameRefusal.ARCHIVED
        if new_name == self.name:
            return RenameRefusal.SAME_NAME
        return None
```

```python
# domain/exceptions.py
class AssetNotFoundError(Exception):
    def __init__(self, asset_id: int) -> None:
        super().__init__(f"asset {asset_id} not found")
        self.asset_id = asset_id
```

## application/

```python
# application/dto.py
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AssetInfo:
    id: int
    name: str
    archived: bool


@dataclass(frozen=True, slots=True)
class RenameResult:
    asset: AssetInfo | None
    refusal: RenameRefusal | None
```

```python
# application/interfaces/gateway.py
from typing import Protocol


class Transaction(Protocol):
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class AssetGateway(Protocol):
    async def get_for_update(self, asset_id: int) -> Asset | None: ...
    async def save(self, asset: Asset) -> None: ...
```

```python
# application/interfaces/view.py
class AssetView(Protocol):
    async def get(self, asset_id: int) -> AssetInfo | None: ...
    async def list(self, *, limit: int, offset: int) -> list[AssetInfo]: ...
```

```python
# application/interactor.py
class AssetInteractor:
    def __init__(self, gateway: AssetGateway, transaction: Transaction) -> None:
        self._gateway = gateway
        self._transaction = transaction

    async def rename(self, asset_id: int, new_name: str) -> RenameResult:
        asset = await self._gateway.get_for_update(asset_id)
        if asset is None:
            await self._transaction.rollback()
            raise AssetNotFoundError(asset_id)
        refusal = asset.rename_refusal(new_name)
        if refusal is not None:
            await self._transaction.rollback()          # TX-01: исход без записи
            return RenameResult(asset=None, refusal=refusal)
        asset.name = new_name
        await self._gateway.save(asset)
        await self._transaction.commit()
        return RenameResult(asset=_info(asset), refusal=None)
```

## adapters/

```python
# adapters/gateway.py — пишет в сессии единицы работы запроса
class SqlAssetGateway:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_update(self, asset_id: int) -> Asset | None:
        row = await self._session.scalar(
            select(AssetRow).where(AssetRow.id == asset_id).with_for_update()
        )
        return None if row is None else row.to_domain()
```

```python
# adapters/view.py — читает своей короткой сессией, не из единицы работы (TX-05)
class SqlAssetView:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
```

## controllers/

```python
# controllers/http.py — разобрать → вызвать → ответить (CTL-01)
router = APIRouter(prefix="/assets", route_class=DishkaRoute)


@router.patch("/{asset_id}")
async def rename_asset(
    asset_id: int, body: RenameBody, interactor: FromDishka[AssetInteractor]
) -> AssetResponse:
    result = await interactor.rename(asset_id, body.name)
    if result.refusal is not None:
        raise HTTPException(409, REFUSAL_TEXT[result.refusal])   # текст — представление
    return AssetResponse.from_info(result.asset)
```

## ioc.py

```python
class AssetsAdaptersProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def gateway(self, session: AsyncSession) -> AssetGateway:        # DI-02
        return SqlAssetGateway(session)

    @provide(scope=Scope.APP)
    def view(self, sessions: async_sessionmaker[AsyncSession]) -> AssetView:
        return SqlAssetView(sessions)


class AssetsInteractorsProvider(Provider):
    interactor = provide(AssetInteractor, scope=Scope.REQUEST)


def assets_providers() -> list[Provider]:
    return [AssetsAdaptersProvider(), AssetsInteractorsProvider()]
```

`Transaction` отдаёт инфраструктура: `def transaction(self, uow: UnitOfWork) -> Transaction`.

## public.py

```python
from app.assets.application.dto import AssetInfo
from app.assets.application.interfaces.view import AssetView

__all__ = ["AssetInfo", "AssetView"]
```

## Контракты import-linter для домена

Скопировать блок из `templates/importlinter.ini`, заменить `assets`.
Каждый новый контракт проверить пробным нарушением: добавить запрещённый
импорт → `lint-imports` должен упасть.

## Тесты домена

```
tests/assets/
  test_domain.py            # правила: без БД (TST-01)
  test_adapters.py          # тестовая БД; без commit — откат (TST-02)
  test_http.py              # через собранное приложение, сеть запрещена (TST-03)
  test_container.py         # контейнер отдаёт Interactor и View (TST-05)
```

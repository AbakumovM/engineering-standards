# Данные и эксплуатация

Правила — `catalog.md`, группа OPS.

## Время и деньги (OPS-01, OPS-02)

```python
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

now = datetime.now(UTC)                                      # не datetime.now() / utcnow()

@dataclass(frozen=True, slots=True)
class Money:
    minor: int                                               # копейки
    currency: str                                            # "RUB"

def apply_discount(price: Money, percent: int) -> Money:     # округление — одно правило, в домене
    value = Decimal(price.minor) * (100 - percent) / 100
    return Money(int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP)), price.currency)
```

- В БД: `timestamptz`, деньги — `bigint` (минорные единицы) или `numeric(12,2)`.
- «Конец дня», «до полуночи» — правило домена с явной зоной (`ZoneInfo("Europe/Moscow")`).

## Настройки (OPS-03)

```python
class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_")
    url: SecretStr                                           # обязательна — без неё не стартуем
    pool_size: int = Field(5, ge=1, le=50)

class Settings(BaseSettings):
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    payments: PaymentSettings = Field(default_factory=PaymentSettings)
```

`Settings()` создаётся один раз в точке сборки; ошибка — при старте, а не
при первом платеже.

## Миграции без простоя (OPS-04)

```python
def upgrade() -> None:
    op.execute("SET lock_timeout = '3s'")                    # не стоять в очереди блокировок
    op.add_column("orders", sa.Column("source", sa.Text(), nullable=True))   # expand: nullable

def upgrade() -> None:                                       # индекс — отдельной ревизией
    with op.get_context().autocommit_block():
        op.create_index("ix_orders_source", "orders", ["source"], postgresql_concurrently=True)
```

| Задача | Порядок |
|---|---|
| Новая обязательная колонка | add nullable → код пишет → бэкфилл пачками → `CHECK NOT VALID` → `VALIDATE` → `SET NOT NULL` |
| Переименование колонки | новая колонка → двойная запись → бэкфилл → чтение из новой → удалить старую (отдельный релиз) |
| Удаление колонки | код перестаёт читать и писать → релиз → `DROP` следующим релизом |
| Индекс на живой таблице | `CONCURRENTLY`, вне транзакции; при сбое — удалить невалидный индекс и повторить |
| Смена типа | новая колонка, как переименование |

Миграция упала по `lock_timeout` — повторить позже, а не поднимать таймаут.

## Выкатка (OPS-05, OPS-06)

1. Миграции (только expand) — до запуска новой версии.
2. Новая версия; старая и новая работают одновременно на одной схеме.
3. Contract-миграции — следующим релизом, когда старой версии нет.
4. Рискованное — за флагом, сначала на тестовых пользователях.

Откат: предыдущая версия кода на текущей схеме. Если откату нужна
обратная миграция — значит, миграция была не expand.

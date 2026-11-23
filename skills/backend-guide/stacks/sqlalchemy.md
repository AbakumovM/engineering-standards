# SQLAlchemy (async) + Alembic

- Строки ORM (`AssetRow`) — в `adapters/` или `infrastructure/db/models.py`, не в `domain/`.
  Адаптер переводит строку в доменную модель (`row.to_domain()`) и обратно. Императивный
  маппинг на доменные классы допустим, но тогда `domain/` всё равно не импортирует SQLAlchemy.
- Единица работы владеет `AsyncSession` запроса (область REQUEST). Gateway получает сессию,
  `commit()` не вызывает (TX-01: коммитит сценарий через порт `Transaction`).
- View — своя короткая сессия из `async_sessionmaker` (TX-05), `expire_on_commit=False`.
- Ленивые загрузки в async запрещены: `lazy="raise"` по умолчанию, нужное — `selectinload`/`joinedload`.
- Ожидаемый конфликт: `async with session.begin_nested()` + `IntegrityError` → доменное исключение (TX-07).
- `MetaData(naming_convention={...})` с `ix_/uq_/ck_/fk_/pk_` (DB-03).
- Engine: `pool_pre_ping=True`, `pool_timeout`, `connect_args` с таймаутом запроса (ADP-01).
- Alembic: autogenerate — только черновик, ревизию читать глазами; миграции не импортируют
  код приложения, кроме метаданных для autogenerate (DB-02). Данные в миграции — SQL, не ORM-модели.

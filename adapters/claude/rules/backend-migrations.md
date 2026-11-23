---
paths:
  - "**/migrations/**/*.py"
  - "**/alembic/**/*.py"
---
# Миграции

- Схему меняют только миграции (DB-02). Миграция не импортирует код приложения.
- Autogenerate — черновик: прочитать ревизию глазами. Имена ограничений — по naming_convention (DB-03).
- Необратимая миграция — явно помечена; данные — SQL, не ORM-модели.
- Без простоя (OPS-04): `SET lock_timeout` в начале; индекс — `CONCURRENTLY` вне транзакции;
  новая колонка — nullable, бэкфилл пачками, `NOT NULL` через `CHECK NOT VALID` → `VALIDATE`;
  без `RENAME`/`DROP` того, что читает текущая версия кода (expand → contract).
- Подробно — `backend-guide/operations.md`.

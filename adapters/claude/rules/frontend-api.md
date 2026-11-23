---
paths:
  - "**/src/features/*/api/**"
  - "**/src/shared/api/**"
  - "**/openapi-ts.config.*"
---
# Данные и API (подробно: frontend-guide/api.md)

- Типы и функции — из `shared/api/generated/` (`pnpm api:generate`), руками не править (FAPI-01).
- Запросы — только через клиент `shared/api`; нет `fetch`/`axios` в фичах (FAPI-02).
- После мутации — `invalidateQueries`/`setQueryData` нужных ключей (FAPI-03).
- Ошибки problem+json → `ApiError` в одном месте; `422` — к полям формы (FAPI-04).
- Список — курсор + `useInfiniteQuery` (FAPI-05).
- Создание/оплата — `Idempotency-Key` на попытку, кнопка заблокирована (FAPI-06).
- Мутации не повторяются; `4xx` не повторяются; `staleTime` задан (FAPI-07, FAPI-08).
- Токены не в `localStorage`; при cookie-сессии — CSRF-заголовок (FSEC-02, FSEC-03).

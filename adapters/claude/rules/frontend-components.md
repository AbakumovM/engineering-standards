---
paths:
  - "**/src/features/**/*.tsx"
  - "**/src/shared/ui/**/*.tsx"
---
# Компоненты (каталог правил: frontend-guide/catalog.md)

- Компонент отображает; «можно ли», статус, сумма — функция в `model/` (FCMP-01).
- Нет `fetch` и загрузки в `useEffect`: `useQuery` с options из `api/` фичи (FCMP-02).
- `useEffect` — только синхронизация с внешним миром; производное — при рендере (FCMP-03).
- Данные сервера не копировать в `useState`/стор (FSTATE-01). `key` — стабильный id (FCMP-04).
- Кнопка — `<button>`, ссылка — `<a>`/`Link`; `label`, `alt`, `aria-label` у иконок (FA11Y-01, FA11Y-03).
- Модалки, меню, списки выбора — из `shared/ui` (shadcn/ui), не самописные (FA11Y-05).
- Нет `dangerouslySetInnerHTML` без DOMPurify; ссылки из данных — `safeHref` (FSEC-01, FSEC-06).
- `shared/ui` не знает о фичах: данные — пропсами (FDEP-02). Чужая фича — через `index.ts` (FDEP-03).

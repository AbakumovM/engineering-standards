---
paths:
  - "**/src/routes/**/*.tsx"
  - "**/src/app/**/*.tsx"
---
# Маршруты и сборка (каталог правил: frontend-guide/catalog.md)

- Маршрут тонкий: `validateSearch` → `loader` → компоненты фич; без бизнес-условий (FSTR-05).
- Search params — схема Zod с `.catch`, неверный параметр не роняет страницу (FRTE-01).
- Данные страницы — `loader` + `ensureQueryData`, в компоненте `useSuspenseQuery` (FRTE-02).
- `beforeLoad` — удобство; права проверяет бэкенд (FRTE-03, FSEC-07).
- У корня — `errorComponent`, `notFoundComponent`; белого экрана нет (FRTE-05, FOBS-01).
- Фильтры, страница, вкладка — в URL (FSTATE-02).

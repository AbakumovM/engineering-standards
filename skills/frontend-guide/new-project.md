# Новый фронтенд-проект

Стек — `frontend.md`, «Стек по умолчанию». Команды и имена пакетов —
на ноябрь 2026; перед установкой сверить с документацией текущих версий
(особенно настройку React Compiler и генератора клиента: они менялись).

## 1. Каркас

```bash
pnpm create vite@latest web --template react-ts
cd web
pnpm add @tanstack/react-router @tanstack/react-query zod react-hook-form @hookform/resolvers
pnpm add -D @tanstack/router-plugin @hey-api/openapi-ts \
  tailwindcss @tailwindcss/vite \
  @vitejs/plugin-react @rolldown/plugin-babel babel-plugin-react-compiler @babel/core \
  eslint @eslint/js typescript-eslint eslint-plugin-react-hooks eslint-plugin-jsx-a11y \
  eslint-plugin-boundaries eslint-import-resolver-typescript eslint-config-prettier prettier \
  vitest jsdom @testing-library/react @testing-library/user-event @testing-library/jest-dom msw \
  @playwright/test @axe-core/playwright knip
pnpm dlx shadcn@latest init          # Tailwind 4, компоненты в src/shared/ui
```

Сбор ошибок (`@sentry/react`), `zustand`, `@tanstack/react-virtual`,
`dompurify` — когда понадобятся, не заранее (FSTR-02).

## 2. Каталоги

```
src/
  app/
    providers.tsx         # QueryClientProvider, RouterProvider
    query-client.ts       # настройки повторов и staleTime (FAPI-07, FAPI-08)
    router.tsx            # createRouter: context { queryClient }, defaultPreload "intent"
    index.css             # @import "tailwindcss"; токены темы
  routes/
    __root.tsx            # errorComponent, notFoundComponent (FRTE-05)
    index.tsx
  features/               # пусто, пока нет первой фичи
  shared/
    api/
      generated/          # pnpm api:generate — не править
      client.ts           # baseUrl, заголовки, разбор problem+json (api.md)
      errors.ts           # ApiError
    ui/                   # shadcn/ui
    config/env.ts
  main.tsx
e2e/
```

## 3. Настройки

Шаблоны — `templates/frontend/` репозитория engineering-standards:
`eslint.config.js`, `tsconfig.app.json`, `openapi-ts.config.ts`,
`knip.json`. Скопировать и поправить пути.

```ts
// vite.config.ts
import path from "node:path";
import babel from "@rolldown/plugin-babel";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    tanstackRouter({ target: "react", autoCodeSplitting: true }), // до react() (FRTE-04)
    react(),
    babel({ presets: [reactCompilerPreset()] }),                   // React Compiler (FCMP-06)
    tailwindcss(),
  ],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  build: { sourcemap: "hidden" },                                  // карты — в сбор ошибок, не на сайт (FOBS-02)
  server: { proxy: { "/api": "http://localhost:8000" } },          // бэкенд локально, тот же origin
});
```

Проверить, что компилятор работает: в React DevTools у компонентов значок
«Memo ✨». Не работает — сверить порядок плагинов с README `@vitejs/plugin-react`.

```jsonc
// package.json — scripts
{
  "dev": "vite",
  "build": "tsc -b && vite build",
  "typecheck": "tsc -b --noEmit",
  "lint": "eslint . --max-warnings 0",
  "format": "prettier --write .",
  "test": "vitest run",
  "test:e2e": "playwright test",
  "knip": "knip",
  "api:generate": "openapi-ts"
}
```

```ts
// src/shared/config/env.ts — ошибка конфигурации при старте, а не в середине работы
const envSchema = z.object({
  VITE_API_URL: z.string().default("/api"),
  VITE_SENTRY_DSN: z.string().url().optional(),
});
export const env = envSchema.parse(import.meta.env);
```

```ts
// src/app/query-client.ts
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) => failureCount < 2 && isRetryable(error),   // api.md
    },
    mutations: { retry: 0 },
  },
});
```

## 4. CI

```bash
pnpm install --frozen-lockfile
pnpm api:generate && git diff --exit-code src/shared/api/generated   # клиент совпадает со схемой (FAPI-01)
pnpm lint && pnpm typecheck && pnpm test && pnpm knip
pnpm build                                                            # + проверка бюджета (FPERF-02)
pnpm test:e2e
pnpm audit --audit-level high                                         # FSEC-08
```

`pnpm-workspace.yaml` (или `.npmrc`, по версии pnpm):
`minimumReleaseAge: 4320` — не ставить пакеты моложе трёх суток (FSEC-08).

## 5. Раздача

Статика за nginx/CDN: `index.html` — `Cache-Control: no-cache`, файлы с
хэшем в имени — `max-age=31536000, immutable`; заголовки безопасности —
`security.md`. Все неизвестные пути → `index.html` (маршрутизация на клиенте).
API на том же origin (`/api` → бэкенд): меньше CORS и проще cookie-сессия.

## 6. AGENTS.md проекта

Шаблон — `templates/AGENTS.md`: состав, команды, «Отклонения от общих
правил». Правила ставятся `./install.sh project <путь> --profile frontend`.

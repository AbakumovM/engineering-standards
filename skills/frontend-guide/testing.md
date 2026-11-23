# Тесты и сбор ошибок

Правила — `catalog.md`, группы FTST, FOBS.

## Что каким тестом

| Что | Чем | Где |
|---|---|---|
| Правила `model/`, разбор ошибок, `safeHref` | Vitest, без DOM | рядом: `*.test.ts` |
| Компонент, форма с запросами | Vitest + Testing Library + MSW (jsdom) | рядом: `*.test.tsx` |
| Главные пути: вход, создание, оплата | Playwright + axe, против собранного приложения и тестового бэкенда или MSW | `e2e/*.spec.ts` |

Компоненту, которому нужен настоящий браузер (размеры, canvas,
drag-and-drop), — режим браузера Vitest (`@vitest/browser-playwright`).

## Настройка

```ts
// vitest.config.ts
export default mergeConfig(viteConfig, defineConfig({
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], restoreMocks: true },
}));

// src/test/setup.ts
import "@testing-library/jest-dom/vitest";
export const server = setupServer(...handlers);
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));   // незамоканный запрос — ошибка теста
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// src/test/render.tsx — провайдеры как в приложении, свежий кэш на каждый тест
export function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}
```

## Тест компонента (FTST-02, FTST-03)

```tsx
it("показывает ошибку сервера у поля", async () => {
  server.use(http.post("*/assets", () =>
    HttpResponse.json(
      { type: "about:blank", title: "Validation", status: 422, errors: [{ field: "name", message: "Уже существует" }] },
      { status: 422, headers: { "Content-Type": "application/problem+json" } },
    ),
  ));
  renderWithProviders(<CreateAssetForm onCreated={vi.fn()} />);

  await userEvent.type(screen.getByLabelText("Название"), "Склад");
  await userEvent.click(screen.getByRole("button", { name: "Создать" }));

  expect(await screen.findByText("Уже существует")).toBeInTheDocument();
});

it("не отправляет форму дважды", async () => {
  let calls = 0;
  server.use(http.post("*/assets", async () => { calls++; await delay(100); return HttpResponse.json(asset(), { status: 201 }); }));
  renderWithProviders(<CreateAssetForm onCreated={vi.fn()} />);
  await userEvent.type(screen.getByLabelText("Название"), "Склад");
  const submit = screen.getByRole("button", { name: "Создать" });
  await userEvent.dblClick(submit);
  await waitFor(() => expect(calls).toBe(1));
});
```

Для каждого запроса — успех и хотя бы одна ошибка (`422`, `409` или `500`).

## e2e (FTST-04, FA11Y-06)

```ts
// e2e/assets.spec.ts
test("создание актива", async ({ page }) => {
  await page.goto("/assets");
  await page.getByRole("button", { name: "Новый актив" }).click();
  await page.getByLabel("Название").fill("Склад");
  await page.getByRole("button", { name: "Создать" }).click();
  await expect(page.getByRole("heading", { name: "Склад" })).toBeVisible();

  const a11y = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(a11y.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
});
```

## Сбор ошибок (FOBS-01…FOBS-05)

```ts
// app/sentry.ts — только если задан DSN
if (env.VITE_SENTRY_DSN) {
  Sentry.init({
    dsn: env.VITE_SENTRY_DSN,
    release: import.meta.env.VITE_RELEASE,           // версия сборки из CI
    environment: import.meta.env.MODE,
    sendDefaultPii: false,                            // FSEC-11
    tracesSampleRate: 0.1,
    beforeSend(event, hint) {
      const error = hint.originalException;
      if (error instanceof ApiError) {
        if (error.status < 500) return null;          // 4xx — не ошибка приложения
        event.tags = { ...event.tags, request_id: error.requestId ?? "none" };   // FOBS-05
      }
      return event;
    },
  });
}
```

Source maps: сборка с `sourcemap: "hidden"`, загрузка в сбор ошибок в CI
(`sentry-cli sourcemaps upload`), затем удаление `*.map` из `dist/`
перед публикацией.

```tsx
// routes/__root.tsx — нет белого экрана (FOBS-01, FRTE-05)
export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: RootLayout,
  errorComponent: ({ error, reset }) => <ErrorScreen error={error} onRetry={reset} />,   // показывает request_id
  notFoundComponent: () => <NotFoundScreen />,
});
```

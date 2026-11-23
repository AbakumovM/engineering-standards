# Данные и API

Правила — `catalog.md`, группа FAPI. Контракт с бэкендом — его OpenAPI и
правила бэкенда (`backend-guide/api.md`): problem+json, курсор,
`Idempotency-Key`, `X-Request-ID`.

## Генерация клиента (FAPI-01)

```ts
// openapi-ts.config.ts
import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: process.env.OPENAPI_URL ?? "http://localhost:8000/openapi.json",   // или файл схемы из репозитория бэкенда
  output: "src/shared/api/generated",
  plugins: ["@hey-api/client-fetch", "zod", "@tanstack/react-query"],
});
```

Бэкенд на FastAPI отдаёт `/openapi.json`. Стабильные `operationId`
(`list_assets`, а не автоматические `list_assets_api_v1_assets_get`) —
настроить на бэкенде (`generate_unique_id_function`), иначе имена функций
длинные и меняются при переносе маршрута.

## Настройка клиента (FAPI-02, FSEC-03)

```ts
// shared/api/client.ts
import { client } from "./generated/client.gen";

client.setConfig({ baseUrl: env.VITE_API_URL, credentials: "include", throwOnError: true });

client.interceptors.request.use((request) => {
  request.headers.set("X-Request-ID", crypto.randomUUID());
  const csrf = readCookie("csrftoken");                      // имя — как договорились с бэкендом
  if (csrf && request.method !== "GET") request.headers.set("X-CSRF-Token", csrf);
  return request;
});

client.interceptors.response.use(async (response, request) => {
  if (response.ok) return response;
  throw await ApiError.fromResponse(response, request.headers.get("X-Request-ID"));
});
```

Таймаут: `AbortSignal.any([signal, AbortSignal.timeout(15_000)])` в
обёртке `fetch` клиента — запрос не висит бесконечно.

## Ошибки (FAPI-04)

```ts
// shared/api/errors.ts
type Problem = { type?: string; title?: string; detail?: string; errors?: { field: string; message: string }[] };

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly problem: Problem,
    readonly requestId: string | null,
    readonly retryAfter: number | null,
  ) {
    super(problem.title ?? `HTTP ${status}`);
  }

  static async fromResponse(response: Response, sentId: string | null): Promise<ApiError> {
    const body: unknown = response.headers.get("content-type")?.includes("json") ? await response.json() : {};
    const problem = problemSchema.safeParse(body);                         // FTS-04
    return new ApiError(
      response.status,
      problem.success ? problem.data : {},
      response.headers.get("X-Request-ID") ?? sentId,
      Number(response.headers.get("Retry-After")) || null,
    );
  }
}

export const isRetryable = (error: unknown) =>
  !(error instanceof ApiError) || error.status >= 500 || error.status === 408 || error.status === 429;
```

| Статус | Что делает фронт |
|---|---|
| `401` | сброс кэша, переход на вход с `?next=<текущий путь>` (проверенный — FSEC-06) |
| `403`, `404` | экран «нет доступа» / «не найдено» в `errorComponent` маршрута |
| `409` | сообщение о конфликте, `invalidateQueries` — показать актуальное |
| `422` | ошибки у полей формы (`state-and-forms.md`) |
| `429`, `503` | «попробуйте позже», повтор не раньше `Retry-After` |
| `5xx`, сеть | общее сообщение с `request_id` и кнопкой «повторить» |

`401` обрабатывается один раз — в `QueryCache`/`MutationCache` `onError`
в `app/query-client.ts`, а не в каждом компоненте.

## Пагинация (FAPI-05)

`useInfiniteQuery` + `getNextPageParam: (page) => page.next_cursor ?? undefined`
(пример — `feature-template.md`). Бесконечная прокрутка — `IntersectionObserver`
на последнем элементе; большие списки — с виртуализацией (FPERF-04).

## Идемпотентность (FAPI-06, FFORM-04)

```ts
// shared/api/idempotency.ts — ключ живёт столько же, сколько попытка пользователя
export function useIdempotencyKey() {
  const [key, setKey] = useState(() => crypto.randomUUID());
  return { key, reset: () => setKey(crypto.randomUUID()) };
}

// в форме
const idem = useIdempotencyKey();
const createAsset = useCreateAsset();

const onSubmit = form.handleSubmit((values) =>
  createAsset.mutate(
    { body: values, headers: { "Idempotency-Key": idem.key } },
    { onSuccess: () => { idem.reset(); form.reset(); } },          // новая попытка — новый ключ
  ),
);
// <Button type="submit" disabled={createAsset.isPending}>
```

Повторная отправка после ошибки сети — тот же ключ: бэкенд вернёт
сохранённый ответ, а не создаст второй объект. Ключ меняется после успеха и
при изменении данных формы (бэкенд ответит `422` на тот же ключ с другим телом).

## Кэш (FAPI-03, FAPI-08)

| Ситуация | Как |
|---|---|
| Мутация вернула объект | `setQueryData(detail.queryKey, obj)` + `invalidateQueries` списков |
| Мутация повлияла на несколько списков | `invalidateQueries({ queryKey: [...префикс] })` |
| Мгновенный отклик (лайк, переключатель) | оптимистичное обновление: `onMutate` → откат в `onError` |
| Выход из аккаунта | `queryClient.clear()` (FSEC-11) |
| Справочники | `staleTime: Infinity` или часы |
| Данные меняются извне (статус оплаты) | `refetchInterval` на время ожидания, не постоянно |

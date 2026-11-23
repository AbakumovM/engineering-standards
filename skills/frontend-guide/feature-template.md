# Шаблон фичи

Пример — фича `assets` (список активов, карточка, создание). Имена
сгенерированных функций зависят от `operationId` в OpenAPI бэкенда и
версии `@hey-api/openapi-ts` — смотреть в `shared/api/generated/`.

```
features/assets/
  api/asset-queries.ts       # options запросов и мутаций
  model/asset-status.ts      # правила отображения
  model/asset-status.test.ts
  model/create-asset-schema.ts
  ui/AssetList.tsx
  ui/AssetCard.tsx
  ui/CreateAssetForm.tsx
  index.ts
routes/assets/index.tsx      # список
routes/assets/$assetId.tsx   # карточка
```

## model/ — правила (FCMP-01, FTST-01)

```ts
// model/asset-status.ts
import type { Asset } from "@/shared/api/generated";

export type ArchiveCheck = { allowed: true } | { allowed: false; reason: "has_active_orders" | "already_archived" };

export function canArchive(asset: Asset): ArchiveCheck {
  if (asset.status === "archived") return { allowed: false, reason: "already_archived" };
  if (asset.active_orders > 0) return { allowed: false, reason: "has_active_orders" };
  return { allowed: true };
}
```

Решает сервер; функция — чтобы не показывать кнопку, которая точно
получит отказ, и объяснить почему.

```ts
// model/asset-status.test.ts
describe("canArchive", () => {
  it("запрещает при активных заказах", () => {
    expect(canArchive(asset({ active_orders: 1 }))).toEqual({ allowed: false, reason: "has_active_orders" });
  });
  it("разрешает без заказов", () => {
    expect(canArchive(asset({ active_orders: 0 }))).toEqual({ allowed: true });
  });
});
```

## api/ — запросы (FAPI-01…FAPI-03)

```ts
// api/asset-queries.ts
import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";
import { createAssetMutation, getAssetOptions, listAssets, listAssetsQueryKey } from "@/shared/api/generated";

export type AssetFilters = { status?: "active" | "archived"; q?: string };

export const assetQueries = {
  list: (filters: AssetFilters) =>
    infiniteQueryOptions({
      queryKey: listAssetsQueryKey({ query: filters }),
      queryFn: async ({ pageParam, signal }) =>
        (await listAssets({ query: { ...filters, cursor: pageParam, limit: 50 }, signal, throwOnError: true })).data,
      initialPageParam: undefined as string | undefined,
      getNextPageParam: (page) => page.next_cursor ?? undefined,      // FAPI-05
    }),
  detail: (assetId: string) => getAssetOptions({ path: { asset_id: assetId } }),
};

export function useCreateAsset() {
  const queryClient = useQueryClient();
  return useMutation({
    ...createAssetMutation(),
    onSuccess: (created) => {
      queryClient.setQueryData(assetQueries.detail(created.id).queryKey, created);
      void queryClient.invalidateQueries({ queryKey: listAssetsQueryKey() });  // FAPI-03
    },
  });
}
```

## ui/ — компоненты (FCMP-02…FCMP-05)

```tsx
// ui/AssetList.tsx
export function AssetList({ filters }: { filters: AssetFilters }) {
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useSuspenseInfiniteQuery(assetQueries.list(filters));
  const assets = data.pages.flatMap((page) => page.items);

  if (assets.length === 0) return <EmptyState title="Активов нет" />;
  return (
    <>
      <ul className="grid gap-3">
        {assets.map((asset) => <li key={asset.id}><AssetCard asset={asset} /></li>)}
      </ul>
      {hasNextPage && (
        <Button onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>Показать ещё</Button>
      )}
    </>
  );
}
```

```tsx
// ui/AssetCard.tsx
const reasonText = { has_active_orders: "Есть активные заказы", already_archived: "Уже в архиве" } as const;

export function AssetCard({ asset }: { asset: Asset }) {
  const check = canArchive(asset);
  return (
    <Card>
      <CardTitle><Link to="/assets/$assetId" params={{ assetId: asset.id }}>{asset.name}</Link></CardTitle>
      {check.allowed ? <ArchiveAssetButton assetId={asset.id} /> : <p className="text-muted-foreground">{reasonText[check.reason]}</p>}
    </Card>
  );
}
```

## index.ts — публичная поверхность (FDEP-03)

```ts
export { AssetList } from "./ui/AssetList";
export { AssetCard } from "./ui/AssetCard";
export { CreateAssetForm } from "./ui/CreateAssetForm";
export { assetQueries, type AssetFilters } from "./api/asset-queries";
```

## routes/ — маршрут (FSTR-05, FRTE-01, FRTE-02)

```tsx
// routes/assets/index.tsx
const searchSchema = z.object({
  status: z.enum(["active", "archived"]).optional().catch(undefined),   // неверный параметр не роняет страницу
  q: z.string().max(100).optional().catch(undefined),
});

export const Route = createFileRoute("/assets/")({
  validateSearch: searchSchema,
  loaderDeps: ({ search }) => search,
  loader: ({ context, deps }) => context.queryClient.ensureInfiniteQueryData(assetQueries.list(deps)),
  component: AssetsPage,
});

function AssetsPage() {
  const filters = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <Page title="Активы">
      <AssetFiltersBar value={filters} onChange={(next) => navigate({ search: next })} />
      <AssetList filters={filters} />
    </Page>
  );
}
```

## Чек-лист новой фичи

- [ ] Правила — в `model/` с тестами; в JSX только вызов.
- [ ] Данные — через options из `api/`; нет `fetch`, `useEffect`-загрузки.
- [ ] Список — курсор; мутация инвалидирует ключи.
- [ ] Создающая мутация — `Idempotency-Key` и блокировка кнопки (`api.md`).
- [ ] Ошибки: `422` у полей, остальное — общим обработчиком.
- [ ] Фильтры — в URL через `validateSearch`.
- [ ] Наружу — только `index.ts`.
- [ ] Тесты: `model/`, компонент с MSW (успех и ошибка), e2e для главного пути.

# Состояние и формы

Правила — `catalog.md`, группы FSTATE, FFORM.

## Где живёт состояние

| Что | Где | Пример |
|---|---|---|
| Данные с сервера | TanStack Query (FSTATE-01) | список активов, профиль |
| Чем делятся ссылкой | search params маршрута (FSTATE-02) | фильтры, сортировка, вкладка, открытая карточка |
| Состояние одного компонента | `useState` / `useReducer` | открыт ли список, ввод до отправки |
| Ввод формы | react-hook-form (FFORM-02) | поля, ошибки, «отправляется» |
| Общее клиентское, несколько страниц | стор Zustand в фиче (FSTATE-03) | корзина, шаги мастера |
| Редко меняющееся, всему дереву | контекст (FSTATE-04) | тема, язык |
| Вычисляемое | ничего не хранить — считать при рендере (FSTATE-05) | итог корзины, «можно ли отправить» |

Порядок выбора: можно вычислить → вычислить; есть на сервере → Query;
нужно в ссылке → URL; нужно одному компоненту → `useState`; только потом стор.

## Стор (FSTATE-03)

```ts
// features/cart/model/cart-store.ts
type CartState = {
  items: CartItem[];
  add: (item: CartItem) => void;
  remove: (productId: string) => void;
  clear: () => void;
};

export const useCartStore = create<CartState>()((set) => ({
  items: [],
  add: (item) => set((s) => ({ items: [...s.items.filter((i) => i.productId !== item.productId), item] })),
  remove: (productId) => set((s) => ({ items: s.items.filter((i) => i.productId !== productId) })),
  clear: () => set({ items: [] }),
}));

// подписка на часть — компонент не перерисуется от остального
const count = useCartStore((s) => s.items.length);
```

В сторе — id и выбор пользователя, не копии объектов с сервера: цены и
названия берутся из Query по id.

## Без лишних эффектов (FCMP-03)

```tsx
// плохо: производное через эффект — лишний рендер, рассинхрон
const [total, setTotal] = useState(0);
useEffect(() => setTotal(items.reduce((s, i) => s + i.price, 0)), [items]);

// хорошо
const total = items.reduce((s, i) => s + i.price, 0);

// плохо: сброс состояния при смене пропса эффектом
useEffect(() => setDraft(""), [assetId]);
// хорошо: новый ключ — новое состояние
<CommentForm key={assetId} assetId={assetId} />
```

## Форма (FFORM-01…FFORM-04)

```ts
// features/assets/model/create-asset-schema.ts
export const createAssetSchema = z.object({
  name: z.string().trim().min(1, "Введите название").max(200),
  price: z.coerce.number().int().positive(),                    // в минорных единицах, как на бэкенде
  tags: z.array(z.string().max(30)).max(10).default([]),
});
export type CreateAssetForm = z.infer<typeof createAssetSchema>;
```

```tsx
// features/assets/ui/CreateAssetForm.tsx
export function CreateAssetForm({ onCreated }: { onCreated: (id: string) => void }) {
  const form = useForm<CreateAssetForm>({ resolver: zodResolver(createAssetSchema), defaultValues: { name: "", price: 0, tags: [] } });
  const idem = useIdempotencyKey();
  const createAsset = useCreateAsset();

  const onSubmit = form.handleSubmit((body) =>
    createAsset.mutate(
      { body, headers: { "Idempotency-Key": idem.key } },
      {
        onSuccess: (asset) => { idem.reset(); onCreated(asset.id); },
        onError: (error) => applyServerErrors(form, error),         // 422 → поля (FFORM-03)
      },
    ),
  );

  return (
    <Form {...form}>
      <form onSubmit={onSubmit} noValidate>
        <FormField control={form.control} name="name" render={({ field }) => (
          <FormItem>
            <FormLabel>Название</FormLabel>
            <FormControl><Input {...field} /></FormControl>
            <FormMessage />
          </FormItem>
        )} />
        <FormRootError />
        <Button type="submit" disabled={createAsset.isPending}>
          {createAsset.isPending ? "Сохраняем…" : "Создать"}
        </Button>
      </form>
    </Form>
  );
}
```

```ts
// shared/api/form-errors.ts
export function applyServerErrors<T extends FieldValues>(form: UseFormReturn<T>, error: unknown) {
  if (error instanceof ApiError && error.status === 422 && error.problem.errors?.length) {
    for (const e of error.problem.errors) form.setError(e.field as Path<T>, { message: e.message });
    return;
  }
  form.setError("root", { message: error instanceof ApiError ? describe(error) : "Не удалось отправить" });
}
```

Компоненты `Form*` — из shadcn/ui (`shared/ui/form`): подпись, ошибка и
`aria-describedby` связаны сами (FA11Y-03). Имена полей в ответе `422`
бэкенда и в схеме формы совпадают — договориться один раз.

## Мастер из нескольких шагов

Шаг — в URL (`?step=2`), введённые данные — в сторе фичи или одной форме
на весь мастер; отправка — одна, в конце, с одним `Idempotency-Key`.

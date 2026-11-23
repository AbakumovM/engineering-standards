# Скорость и доступность

Правила — `catalog.md`, группы FPERF, FA11Y.

## Цели (FPERF-03)

| Метрика | Хорошо (p75) | Что ухудшает |
|---|---|---|
| LCP — главный контент показан | ≤ 2,5 с | большой бандл, каскад запросов, тяжёлая картинка без приоритета, шрифты |
| INP — отклик на действие | ≤ 200 мс | долгие обработчики, перерисовка большого дерева, тысячи DOM-узлов |
| CLS — сдвиги макета | ≤ 0,1 | картинки без размеров, поздно вставленные баннеры, шрифты без запасного |

```ts
// app/web-vitals.ts
import { onCLS, onINP, onLCP } from "web-vitals";
const send = (metric: Metric) => navigator.sendBeacon("/api/rum", JSON.stringify({ name: metric.name, value: metric.value, id: metric.id, path: location.pathname }));
onCLS(send); onINP(send); onLCP(send);
```

## Что делать по порядку

1. **Каскады запросов.** Данные страницы — в `loader` (FRTE-02),
   независимые запросы — параллельно, `preload: "intent"` на ссылках.
2. **Бандл.** `autoCodeSplitting`; редкое тяжёлое (редактор, графики,
   экспорт) — `lazy(() => import(...))`. Отчёт: `pnpm dlx vite-bundle-visualizer`.
3. **Списки.** > ~200 строк — `@tanstack/react-virtual` или пагинация.
4. **Ввод.** Поиск — `useDeferredValue` или debounce 200–300 мс; тяжёлое
   обновление — `startTransition`.
5. **Картинки и шрифты.** Размеры, `loading="lazy"`, WebP/AVIF, свои шрифты
   с `font-display: swap`, `<link rel="preload">` для главного.
6. **Перерисовки** — только после замера в React Profiler (FCMP-06).

Бюджет в CI (FPERF-02):

```jsonc
// package.json
"size-limit": [{ "path": "dist/assets/index-*.js", "limit": "200 KB" }]
```

## Доступность (FA11Y)

Цель — WCAG 2.2 AA. Большую часть даёт правильная разметка и готовые
примитивы shadcn/ui (Radix).

```tsx
// плохо
<div onClick={archive} className="btn">В архив</div>
<img src={asset.photo} />
<button onClick={close}><XIcon /></button>
<input placeholder="Email" />

// хорошо
<Button type="button" onClick={archive}>В архив</Button>
<img src={asset.photo} alt={asset.name} width={320} height={240} />
<Button variant="ghost" size="icon" aria-label="Закрыть" onClick={close}><XIcon aria-hidden /></Button>
<Label htmlFor="email">Email</Label><Input id="email" type="email" autoComplete="email" />
```

| Проверить | Как |
|---|---|
| Всё доступно с клавиатуры | пройти страницу `Tab`/`Shift+Tab`/`Enter`/`Esc` без мыши |
| Фокус виден | нет `outline: none` без `focus-visible:` замены |
| Модалка | фокус внутрь при открытии, обратно на кнопку при закрытии, `Esc` закрывает |
| Подписи | у полей `label`, у иконок-кнопок `aria-label`, у картинок `alt` |
| Состояния | ошибка/статус — текстом, не только цветом; контраст ≥ 4,5:1 |
| Динамика | сообщения после действий — `role="status"` / тост с `aria-live` |
| Язык | `<html lang="ru">` |
| Автоматически | jsx-a11y в линтере, axe в e2e (`testing.md`) |

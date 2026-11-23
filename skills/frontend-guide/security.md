# Безопасность фронтенда

Правила — `catalog.md`, группа FSEC. Главное: фронт — код на чужом
компьютере. Всё, что он проверяет, проверяется и на сервере; всё, что в нём
лежит, — публично.

## Вход и сессия (FSEC-02, FSEC-03)

| Схема | Когда | Что на фронте |
|---|---|---|
| Cookie-сессия от бэкенда (по умолчанию) | свой бэкенд, тот же сайт | `credentials: "include"`, CSRF-заголовок на изменяющих запросах, токенов в JS нет |
| BFF (сервер-посредник) для OAuth/OIDC | вход через внешнего провайдера | BFF хранит токены, браузеру — HttpOnly-cookie; как выше |
| Access token в памяти | только если бэкенд не умеет cookie | токен в замыкании модуля клиента, короткий; обновление — HttpOnly refresh-cookie; после перезагрузки — тихое обновление |

Никогда: токен в `localStorage`, `sessionStorage`, IndexedDB, URL,
незащищённой cookie, сторе с `persist`.

Cookie сессии (ставит бэкенд): `HttpOnly; Secure; SameSite=Lax` (или
`Strict`), `Path=/`, без `Domain`, имя с префиксом `__Host-`.

Выход: запрос на бэкенд (он удаляет сессию) → `queryClient.clear()` →
сброс сторов → переход на вход.

## HTML и ссылки из данных (FSEC-01, FSEC-06)

```tsx
// HTML, без которого нельзя (письмо, статья из редактора)
import DOMPurify from "dompurify";
<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(article.html) }} />  // arch-ignore[FSEC-01]: очищено DOMPurify

// ссылка из данных
export function safeHref(url: string): string | undefined {
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : undefined;
  } catch { return undefined; }
}

// редирект после входа: только свой origin
export function safeNext(next: string | undefined): string {
  if (!next) return "/";
  const url = new URL(next, window.location.origin);
  return url.origin === window.location.origin ? url.pathname + url.search : "/";
}
```

Внешние ссылки: `target="_blank"` с `rel="noopener noreferrer"`.

## Секреты и окружение (FSEC-04)

`import.meta.env.VITE_*` встраивается в бандл как есть. Допустимо: URL API,
DSN сбора ошибок, публичный ключ платёжного виджета, флаги. Недопустимо:
секретные ключи платёжек, токены ботов, ключи облаков, пароли — их
использует бэкенд.

## Заголовки раздачи (FSEC-05)

```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://<sentry-host>; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
```

Внедрять так: `Content-Security-Policy-Report-Only` → собрать нарушения →
включить. `style-src 'unsafe-inline'` часто нужен библиотекам стилей; для
скриптов — никогда.

## Зависимости (FSEC-08)

Перед `pnpm add`:
1. Нужна ли — может, хватит стандартной библиотеки или того, что есть.
2. Поддерживается (релизы за последний год, отвечают на issues), сколько
   транзитивных зависимостей, размер (FPERF-06).
3. Имя пакета точное (тайпсквоттинг: `reactt`, `lodahs`).

В CI: `--frozen-lockfile`, `pnpm audit`. pnpm 10 по умолчанию не запускает
скрипты установки — разрешать по одному (`onlyBuiltDependencies`).

## Чек-лист перед мержем

- [ ] Нет `dangerouslySetInnerHTML`/`innerHTML` с данными без DOMPurify.
- [ ] Нет токенов и персональных данных в хранилище браузера и URL.
- [ ] Нет секретов в `VITE_*` и в коде.
- [ ] Ссылки и редиректы из данных проверены.
- [ ] `postMessage` — с проверкой `origin` и `targetOrigin`.
- [ ] Скрытые от роли кнопки — бэкенд тоже запрещает это действие.
- [ ] Новые зависимости — проверены по списку выше.

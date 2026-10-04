# Academic homepage — Daniil Golubenko

Сайт: https://dgolubenko.d-golubenko31.workers.dev/

## Обновление сайта

Cloudflare Workers Builds подключён к приватному репозиторию dgolubenko99/academic-homepage. Изменения в ветке main автоматически публикуются. Команда публикации: `npx wrangler deploy`. Отдельная сборка не нужна.

Можно менять содержание через Codex или через GitHub: открыть файл → Edit → Commit changes. Локальное сохранение в Блокноте само по себе не обновляет GitHub.

## Статистика

- Браузерные посещения, страницы и источники: Cloudflare → Observability → Analytics → Web analytics → dgolubenko.d-golubenko31.workers.dev.
- Запросы ботов: Workers & Pages → dgolubenko → Observability. Фильтр `event = site_visit`, затем `category = ai_bot` или по полю `agent`. Метрики Workers включают все запросы, в том числе CSS и перенаправления; для просмотров страниц фильтруйте `content_type = text/html`, `method = GET`, `status = 200`.
- Категория определяется по User-Agent, который можно подделать. `browser_or_unknown` не гарантирует, что это человек. Посещение ботом не доказывает индексирование или цитирование в ответе LLM.
- На бесплатном плане журналы сейчас хранятся 3 дня, до 200 000 записей в сутки. Это оперативный журнал ботов, не долгосрочный архив. Лимит Workers Free — 100 000 запросов в сутки; запросы через worker.js учитываются в нём.

worker.js не записывает IP, cookies, query string или полный User-Agent. Доступ к аналитике только в аккаунте Cloudflare. Ключ деплоя имеет Workers Scripts Edit и разрешения чтения Account Settings, Memberships, User Details.

## Поисковые боты

Все научные тексты находятся в HTML без необходимости исполнять JavaScript. robots.txt разрешает обход; sitemap.xml и canonical указывают опубликованные адреса. При добавлении страницы обновите sitemap.xml.

.assetsignore публикует только HTML, styles.css, robots.txt и sitemap.xml. Исходные рукописи, README и worker.js не доступны как статические файлы сайта.

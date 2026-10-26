# Начни отсюда: перенос бота на бесплатный сервер (Render)

Ты зарегистрировал GitHub и Cloudflare. **Идём через GitHub + Render** — это 10–15 минут,
без карты. Cloudflare пока отложим: с июня 2025 российские провайдеры тротлят сайты
за Cloudflare (официально [признано Cloudflare](https://developers.cloudflare.com/support/troubleshooting/general-troubleshooting/service-disruption/)),
а мини-приложение открывается у российских пользователей — оно может не загрузиться.
Cloudflare пригодится позже, если появятся пользователи не из РФ или свой домен.

Важно: **сначала перевыпусти токен бота** (@BotFather → /mybots → бот → API Token → /revoke).
Новый токен вводится уже в Render, старый в переписке/архиве станет бесполезен.

---

## Шаг 1. GitHub: создать репозиторий

1. https://github.com/new
2. Repository name: `ton-swap-bot`
3. Выбери **Private** → **Create repository**.
4. Ничего не добавляй (README, .gitignore — не надо).

## Шаг 2. GitHub: загрузить файлы

1. Распакуй `ton-swap-bot-deploy.zip` в любую папку. Внутри будет папка `ton-swap-bot`.
2. На странице пустого репозитория нажми **uploading an existing file**
   (или **Add file → Upload files**).
3. Открой распакованную папку `ton-swap-bot`, выдели **всё содержимое**
   (папки `bot`, `webapp`, `deploy`, `tests`, `tools` и файлы `render.yaml`,
   `requirements.txt`, `README.md` и т.д.) и перетащи в браузер.
   В самом архиве нет `.env` — секреты туда не попадут.
4. Внизу нажми **Commit changes**.

Проверка: в репозитории видно `render.yaml` и папку `bot`; файла `.env` нет.

## Шаг 3. Render: подключить репозиторий

1. https://render.com → **Get Started** → **GitHub** → разреши доступ.
   Если Render попросит выбрать репозитории — дай доступ к `ton-swap-bot`.
2. В панели Render: **New → Blueprint**.
3. Выбери репозиторий `ton-swap-bot` → **Connect**.
4. Render прочитает `render.yaml` и покажет сервис `ton-swap-bot`.
   Он спросит два секрета:
   - `BOT_TOKEN` — новый токен из @BotFather;
   - `TONAPI_KEY` — ключ из tonconsole (можно пока оставить старый, но лучше перевыпустить).
5. **Apply** (или **Create**). Сборка 3–5 минут.

## Шаг 4. Проверить

Render покажет адрес вида `https://ton-swap-bot-xxxx.onrender.com`.

1. Открой `https://АДРЕС/api/health` → должно быть `{"ok": true, "bot": "fastobmennik_bot"}`.
2. Открой бота в Telegram → `/start` → должна прийти кнопка «Открыть обменник» и курс.
3. Нажми кнопку → откроется мини-приложение с кошельком.

Пришли мне этот адрес — я проверю все ручки снаружи и подскажу, если что-то не так.

## Шаг 5. Чтобы не засыпал (важно)

Free-сервис Render засыпает через ~15 минут без запросов. Пинг раз в 10 минут решает:

1. https://cron-job.org → регистрация (бесплатно, без карты).
2. **Create cronjob**:
   - Title: `ton-swap-bot`;
   - URL: `https://АДРЕС/api/health`;
   - Schedule: **every 10 minutes**.
3. Save.

При 31 дне 10-минутный пинг — это 744 часа, лимит Render — 750 часов/мес. Влезает.

## Шаг 6. Выключить локальную копию

Когда Render заработает, на ноутбуке выполни в папке проекта:

```powershell
.\tools\stop-stack.ps1
```

И убери из автозагрузки ярлык `fastobmennik.lnk`
(`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`), иначе бот будет
работать в двух местах и Telegram начнёт отдавать конфликт `409` одному из них.

---

## Если что-то пошло не так

| Симптом | Что делать |
|---|---|
| Render: build failed | пришли лог сборки (вкладка **Logs**) — поправлю Dockerfile |
| `/api/health` не открывается | подожди 2–3 минуты после деплоя, проверь ещё раз |
| бот молчит | Render → Logs: ищи `не удалось связаться с Telegram API` (значит нужен `PROXY_URL` — но из Франкфурта обычно не нужен) |
| мини-приложение пустое | открой `/tonconnect-manifest.json` — там должен быть адрес Render, а не `example.com` |

Запасные варианты (без карты): **Koyeb** (засыпает через час, пинг раз в 20 минут) —
шаги в `DEPLOY-FREE.md`. **Oracle** (нужна карта, зато железный 24/7) — `DEPLOY-ORACLE.md`.

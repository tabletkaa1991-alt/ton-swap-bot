# TON ⇄ USDT — бот-обменник (мини-приложение)

Бот открывает мини-приложение с TON Connect: пользователь подключает свой кошелёк,
видит курс, комиссию и лимиты, обмен подписывает сам. **Средства и ключи остаются у пользователя** —
бот не кастодиальный, фиат не принимает.

## ⚠️ Безопасность

- Секреты только в `.env` (файл в `.gitignore`), никогда — в коде, в переписке и в архивах.
- Токен, попавший в чат или лог, считается скомпрометированным: @BotFather → `/revoke`.
- `TONAPI_KEY` можно ограничить проектом в tonconsole; для свопов ключ не нужен вовсе.

## Как устроено

Один процесс (`python -m bot.main`) и один порт — этого достаточно и для ноутбука,
и для бесплатного хостинга:

| Что | Где |
|---|---|
| Мини-приложение (статика), манифест TON Connect на лету | `bot/web.py` + `webapp/` |
| `/api/health`, `/api/config`, `/api/report` | `bot/web.py` |
| Приём вебхука Telegram (`WEBHOOK_URL`) или long polling | `bot/main.py` |
| Бот: команды, курс, кнопка WebApp | `bot/main.py`, `bot/rates.py` |
| Проверка initData и уведомление с галочкой | `bot/report.py` |
| Бесплатный сервер: Render/Koyeb/Oracle/Workers | `DEPLOY-FREE.md` |

## Что уже работает

| Часть | Статус |
|---|---|
| Бот: `/start`, `/rate`, `/fee`, `/help`, кнопка WebApp, меню «Обмен» | ✅ |
| Курс TON/USD через tonapi | ✅ проверено на живом API |
| Комиссия 2,5% и расчёт «на руки» | ✅ + юнит-тесты |
| Лимиты сделки 1–5000 $ (долларовый эквивалент) | ✅ бот + мини-приложение |
| Мини-приложение: TON Connect, ввод суммы, расчёт, лимиты | ✅ |
| Своп TON → USDT и USDT → TON через STON.fi | ✅ проверено на mainnet-котировках |
| Уведомление об успешном обмене одним сообщением с галочкой | ✅ `POST /api/report` |
| Единый контейнер: статика + API + бот | ✅ `deploy/Dockerfile` |
| Деплой на бесплатный сервер | ✅ `DEPLOY-FREE.md` (Render/Koyeb без карты) |
| Учёт сделок и история на сервере | ⛔ этап 3 |
| Фиат (рубли/доллары на карту) | ⛔ вне проекта: см. ниже |

## Запуск локально (Windows, как раньше)

```powershell
cd ton-swap-bot
.\start.ps1
```

`start.ps1` сначала запускает бота (он занимает 8080 и отдаёт мини-приложение, `/api/*`
и кнопку меню), затем поднимает туннель — **tunnelmole**, при неудаче **cloudflared** —
и перезапускает бота с полученным `https://`‑адресом. Node больше не нужен.

Если `api.telegram.org` не отвечает (типично для российских провайдеров) — включите VPN
или впишите `PROXY_URL` в `.env`; `start.ps1` предупредит об этом заранее.

Бот живёт, пока открыто окно/включён ноутбук; для работы 24/7 — переезд на сервер.

## Тесты

```powershell
$env:PYTHONPATH='vendor'
python -m unittest discover -s tests -v
```

Или в обычном venv: `python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt`.

## Деплой на сервер

### Бесплатно, без карты — Render или Koyeb

Готовый архив проекта без секретов и без мусора — `ton-swap-bot-deploy.zip` (в корне).
Git на компьютере не установлен, поэтому файлы можно загрузить в GitHub прямо через
браузер (drag & drop), инструкция — в **[DEPLOY-FREE.md](DEPLOY-FREE.md)**.

Коротко: залить репозиторий в GitHub → Render Blueprint (`render.yaml`) → ввести
`BOT_TOKEN` и `TONAPI_KEY` → готово, бот сам определит свой адрес.
Подробно, с пингом против засыпания и чек-листом: **[DEPLOY-FREE.md](DEPLOY-FREE.md)**.

### VPS с доменом (Oracle Always Free или любой Ubuntu)

```bash
scp -r ton-swap-bot user@SERVER_IP:/opt/ton-swap-bot
cd /opt/ton-swap-bot
DOMAIN=swap.example.com bash deploy/install.sh
```

`install.sh` поставит Docker, откроет 80/443, соберёт единый контейнер, поднимет Caddy
с сертификатом Let's Encrypt и проверит `/api/health`. Домен с A-записью на IP нужен заранее.
Пошаговая регистрация в Oracle — `DEPLOY-ORACLE.md`.

## Ключи

| Что | Где взять |
|---|---|
| `BOT_TOKEN` | @BotFather → `/newbot` |
| `TONAPI_KEY` | [tonconsole.com](https://tonconsole.com) → проект → API keys |
| альтернатива | @tonapibot → `/get_api_key` (toncenter) |
| DEX | STON.fi — публичные API, ключ не нужен |

## Своп TON ⇄ USDT

Реализация — `webapp/swap-stonfi.js` (точка входа — `webapp/swap.js`), проверена на живом
mainnet-API: котировка → сборка сообщения через `@ston-fi/sdk` v2_2 → BOC в кошелёк.

1. `POST https://api.ston.fi/v1/swap/simulate` (параметры в query string) — курс, `min_ask_units`,
   адреса роутера и пула.
2. `@ston-fi/sdk` (v2_2, тип `CPI`) собирает сообщение: `getSwapTonToJettonTxParams` для TON → USDT,
   `getSwapJettonToTonTxParams` для USDT → TON (нужен адрес USDT-кошелька из tonapi).
3. `tonConnectUI.sendTransaction({ validUntil: now + 5 мин, messages })` — пользователь подписывает.

**Комиссия 2,5%** — вторым сообщением в том же подтверждении, на `SERVICE_WALLET`
(в `webapp/config.js` и `bot`-конфиге). В некастодиальной схеме вычесть комиссию из суммы нельзя:
своп исполняет DEX между пулом и кошельком пользователя. Пока `SERVICE_WALLET` пуст,
комиссия не взимается.

## Чего этот проект не делает

- Не принимает рубли/доллары и не переводит их в крипту: приём фиата — лицензируемая
  деятельность (AML/KYC, эквайринг, отчётность), её нельзя закрыть кодом бота.
- Не продаёт Telegram Stars: звёзды не передаются между аккаунтами, перепродажа запрещена.
- Не хранит пользовательские ключи и средства.

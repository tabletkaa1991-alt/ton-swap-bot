// Мини-приложение обмена TON ⇄ USDT.
//
// Кошелёк подключается через TON Connect, обмен подписывает пользователь.
// Своп — в swap.js (реализация swap-stonfi.js), см. README «Этап 2».

import { FEE_PERCENT, MAX_USD, MIN_USD } from "./config.js?v=20261026";
// ?v= — обход кеша Telegram WebView: после деплоя старый config.js может жить
// в кеше до часа. При изменении статики версию в этом импорте и в index.html
// (src app.js) нужно поднять.

const TONAPI_RATES = "https://tonapi.io/v2/rates?tokens=ton&currencies=usd";
const MANIFEST_URL = new URL("./tonconnect-manifest.json", location.href).href;
let BOT_URL = "https://t.me/fastobmennik_bot"; // перезаписывается из /api/config ниже

// Лимиты — с сервера (/api/config): config.js остаётся фолбэком, если сервер
// не ответил. Так лимит меняется в Render без пересборки статики и не залипает
// в кеше мини-приложения.
const LIMITS = { min: MIN_USD, max: MAX_USD, fee: FEE_PERCENT };

const ui = {
  direction: document.getElementById("direction"),
  amount: document.getElementById("amount"),
  rate: document.getElementById("rate"),
  fee: document.getElementById("fee"),
  receive: document.getElementById("receive"),
  swap: document.getElementById("swap"),
  status: document.getElementById("status"),
  toc: document.getElementById("toc"),
  total: document.getElementById("total"),
  hint: document.getElementById("hint"),
};

const state = {
  connectButton: null,
  rate: null,
  wallet: null,
  busy: false,
};

function formatMoney(value, digits = 2) {
  return Number(value).toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/**
 * Сообщить боту об успешном обмене. Вне Telegram отчёт не нужен: подписи
 * initData нет, и бот не смог бы понять, в какой чат писать.
 */
async function reportSwap(details) {
  const initData = window.Telegram?.WebApp?.initData;
  if (!initData || !details) return;
  try {
    const response = await fetch("api/report", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ initData, details }),
    });
    if (!response.ok) console.warn("report failed:", response.status);
  } catch (error) {
    console.warn("report failed:", error);
  }
}

/** Ссылка на бота и лимиты приходят с бэкенда: имя бота может меняться. */
async function loadPublicConfig() {
  try {
    const response = await fetch("api/config");
    if (!response.ok) return;
    const data = await response.json();
    if (data.botUrl) BOT_URL = data.botUrl;
    if (Number.isFinite(data.feePercent)) LIMITS.fee = data.feePercent;
    if (Number.isFinite(data.minUsd)) LIMITS.min = data.minUsd;
    if (Number.isFinite(data.maxUsd)) LIMITS.max = data.maxUsd;
    render();
  } catch (error) {
    console.warn("config failed:", error);
  }
}

function shortAddress(address) {
  return address.length > 10 ? `${address.slice(0, 4)}…${address.slice(-4)}` : address;
}

function setStatus(text, kind = "") {
  ui.status.textContent = text;
  ui.status.className = kind;
}

/**
 * Десктопный Telegram (Windows/macOS/Linux) и Telegram Web не умеют открывать
 * кошельки: TON Connect рисует список, но нажатия никуда не ведут. Предупреждаем
 * и даём ссылку на бота, чтобы открыть мини-приложение с телефона.
 */
function showPlatformHint() {
  const tg = window.Telegram?.WebApp;
  const platform = tg?.platform ?? "browser";
  const desktop = ["tdesktop", "macos", "web", "weba", "linux"].includes(platform);
  const noInitData = Boolean(tg) && !tg.initData;
  if (!desktop && !noInitData) return;

  const lines = [];
  if (desktop) {
    lines.push(
      "Мини-приложение открыто в <b>десктопном Telegram</b> — он не умеет открывать кошельки, " +
        "поэтому список не реагирует. Открой бота с телефона: " +
        '<a href="' + BOT_URL + '" target="_blank" rel="noreferrer">' + BOT_URL + "</a>",
    );
  }
  if (noInitData) {
    lines.push("Telegram не передал initData — страница открыта не из бота, кошельки в этом режиме недоступны.");
  }
  ui.hint.innerHTML = lines.join("<br><br>");
  ui.hint.hidden = false;

  const button = document.createElement("button");
  button.className = "ghost";
  button.textContent = "Открыть бота в Telegram";
  button.addEventListener("click", () => {
    if (tg?.openTelegramLink) tg.openTelegramLink(BOT_URL);
    else window.open(BOT_URL, "_blank", "noreferrer");
  });
  ui.toc.appendChild(button);
}

function amountUnit() {
  return Number.parseFloat(ui.amount.value.replace(",", ".")) || 0;
}

/** Долларовый эквивалент введённой суммы. */
function amountUsd() {
  if (state.rate === null) return null;
  const amount = amountUnit();
  return ui.direction.value === "ton-usdt" ? amount * state.rate : amount;
}

function limitError() {
  const usd = amountUsd();
  if (usd === null) return "Курс ещё не получен.";
  if (usd <= 0) return "Введите сумму больше нуля.";
  if (usd < LIMITS.min) return `Минимальная сумма сделки — ${LIMITS.min} $ (сейчас ${formatMoney(usd)} $).`;
  if (usd > LIMITS.max) return `Максимальная сумма сделки — ${LIMITS.max} $ (сейчас ${formatMoney(usd)} $).`;
  return null;
}

async function loadRate() {
  try {
    const response = await fetch(TONAPI_RATES, { headers: { accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const price = payload?.rates?.TON?.prices?.USD;
    if (!price) throw new Error("нет цены в ответе");
    state.rate = Number(price);
    ui.rate.textContent = `1 TON ≈ ${formatMoney(state.rate)} $`;
  } catch (error) {
    state.rate = null;
    ui.rate.textContent = "курс недоступен";
    setStatus(`Не удалось получить курс: ${error.message}`, "error");
  }
  render();
}

function render() {
  const amount = amountUnit();
  const toUsdt = ui.direction.value === "ton-usdt";
  // Своп отправляет ровно введённую сумму, поэтому на выходе — полная котировка.
  // Комиссия сервиса списывается отдельным переводом в TON, сверху.
  const fee = toUsdt ? (amount * LIMITS.fee) / 100 : 0;
  const gasTon = 0.31; // форвард-газ свопа; часть вернётся как сдача
  ui.fee.textContent = toUsdt ? `${formatMoney(fee, 4)} TON (${LIMITS.fee}%)` : `${LIMITS.fee}% от суммы`;

  if (state.rate === null) {
    ui.receive.textContent = "—";
    ui.total.textContent = "—";
  } else if (toUsdt) {
    ui.receive.textContent = `${formatMoney(amount * state.rate)} USDT`;
    ui.total.textContent = `${formatMoney(amount + fee + gasTon, 3)} TON`;
  } else {
    ui.receive.textContent = `${formatMoney(amount / state.rate, 4)} TON`;
    ui.total.textContent = `${formatMoney(amount, 2)} USDT + газ`;
  }

  const problem = limitError();
  ui.swap.disabled = Boolean(problem) || state.rate === null || !state.wallet || state.busy;
  ui.swap.textContent = state.wallet ? "Обменять" : "Сначала подключите кошелёк";
  if (state.connectButton) {
    state.connectButton.textContent = state.wallet
      ? `Кошелёк ${shortAddress(state.wallet)} — отключить`
      : "Подключить кошелёк";
  }
  if (problem && !state.busy) setStatus(problem, "error");
  else if (state.rate !== null && !state.busy) {
    const note = toUsdt
      ? " Часть газа вернётся на кошелёк как сдача."
      : " Газ сети списывается в TON сверх суммы.";
    setStatus(`Лимит сделки: ${LIMITS.min}–${LIMITS.max} $.${note}`);
  }
}

async function initTonConnect() {
  if (!window.TON_CONNECT_UI) {
    setStatus("Не удалось загрузить TON Connect — проверьте соединение.", "error");
    return;
  }
  // Внутри Telegram кошельки возвращают пользователя в мини-приложение через
  // twaReturnUrl: это ссылка на бота, а не origin страницы. С origin «Telegram Wallet»
  // не находит, куда вернуться, и подключение молча не завершается.
  const inTelegram = Boolean(window.Telegram?.WebApp?.initData);
  const tonConnectUI = new window.TON_CONNECT_UI.TonConnectUI({
    manifestUrl: MANIFEST_URL,
    ...(inTelegram ? { uiOptions: { twaReturnUrl: BOT_URL } } : {}),
  });
  // onStatusChange без обработчика ошибок молчит: любая проблема с восстановлением
  // сессии выглядела бы как «кошелёк не подключился». Плюс опрашиваем сам wallet —
  // в Telegram WebView событие иногда приходит уже после возврата из кошелька.
  const syncWallet = () => {
    const wallet = tonConnectUI.wallet;
    const address = wallet?.account?.address ?? null;
    if (address !== state.wallet) {
      state.wallet = address;
      render();
    }
  };

  tonConnectUI.onStatusChange(
    (wallet) => {
      state.wallet = wallet?.account?.address ?? null;
      render();
    },
    (error) => {
      setStatus(`Кошелёк: ${error?.message ?? error}`, "error");
    },
  );

  syncWallet();
  setInterval(syncWallet, 2000);
  window.__tonConnectUI = tonConnectUI;

  const button = document.createElement("button");
  button.className = "ghost";
  button.id = "connect-button";
  button.addEventListener("click", () => {
    if (state.wallet) tonConnectUI.disconnect().catch(() => {});
    else tonConnectUI.openModal();
  });
  ui.toc.appendChild(button);
  state.connectButton = button;
  render();
}

ui.amount.addEventListener("input", render);
ui.direction.addEventListener("change", render);
ui.swap.addEventListener("click", async () => {
  if (state.busy) return;
  const problem = limitError();
  if (problem) {
    setStatus(problem, "error");
    return;
  }
  state.busy = true;
  render();
  try {
    const { buildSwap } = await import("./swap.js");
    const result = await buildSwap({
      direction: ui.direction.value,
      amount: amountUnit(),
      usdValue: amountUsd(),
      feePercent: LIMITS.fee,
      minUsd: LIMITS.min,
      maxUsd: LIMITS.max,
      wallet: state.wallet,
      tonConnectUI: window.__tonConnectUI,
    });
    setStatus(result.message, result.ok ? "ok" : "error");
    if (result.ok) await reportSwap(result.details);
  } catch (error) {
    setStatus(`Ошибка обмена: ${error.message}`, "error");
  } finally {
    state.busy = false;
    render();
  }
});

window.Telegram?.WebApp?.expand?.();
window.Telegram?.WebApp?.ready?.();

await loadPublicConfig();
showPlatformHint();
initTonConnect();
loadRate();
setInterval(loadRate, 30_000);

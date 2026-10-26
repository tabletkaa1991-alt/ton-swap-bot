// Адаптер свопа TON ⇄ USDT через STON.fi.
//
// Логика проверена в Node на mainnet-котировках (см. tools/probe-*.mjs и README):
// simulate → @ston-fi/sdk v2_2 (CPI router) → getSwapTonToJettonTxParams /
// getSwapJettonToTonTxParams → сообщение для TON Connect.
//
// SDK грузим с esm.sh, чтобы не собирать бандл. Если esm.sh недоступен —
// см. README, «Сборка бандла вместо esm.sh».

import { SERVICE_WALLET } from './config.js';

const STON_API = 'https://api.ston.fi/v1/swap/simulate';
const TONAPI = 'https://tonapi.io/v2';

// Адреса mainnet
const USDT = 'EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs';
const PTON_MASTER = 'EQBnGWMCf3-FZZq1W4IWcWiGAc3PHuZ0_H-7sad2oY00o83S';

// Минимум газа для свопа USDT → TON (плюс сам перевод жетона).
const JETTON_SWAP_VALUE = 300_000_000n;

const SdkUrls = {
  sdk: 'https://esm.sh/@ston-fi/sdk@2.7.0',
  core: 'https://esm.sh/@ton/core@0.60.0',
};

let sdkPromise = null;
async function loadSdk() {
  if (!sdkPromise) {
    sdkPromise = Promise.all([import(SdkUrls.sdk), import(SdkUrls.core)]).then(([sdk, core]) => ({ ...sdk, ...core }));
  }
  return sdkPromise;
}

/** Провайдер-заглушка: методы контрактов принимают provider первым аргументом. */
function stubProvider() {
  const provider = {
    open: (contract) =>
      new Proxy(contract, {
        get(target, prop) {
          const value = target[prop];
          if (typeof value !== 'function') return value;
          return (...args) => value.call(target, provider, ...args);
        },
      }),
  };
  return provider;
}

/** Отправить транзакцию и перевести типичные ошибки кошелька на человеческий язык. */
async function sendWithFriendlyErrors(tonConnectUI, payload) {
  try {
    await tonConnectUI.sendTransaction(payload);
  } catch (error) {
    const text = String(error?.message ?? error);
    if (/insufficient|not enough|недостаточно|balance|funds/i.test(text)) {
      const total = payload.messages.reduce((sum, m) => sum + BigInt(m.amount), 0n);
      throw new Error(
        `Недостаточно TON на кошельке: для этой сделки нужно ≈${(Number(total) / 1e9).toFixed(3)} TON с учётом газа сети.`,
      );
    }
    if (/reject|cancel|denied|отмен/i.test(text)) throw new Error("Сделка отменена в кошельке.");
    throw new Error(text.length > 200 ? text.slice(0, 200) + "…" : text);
  }
}

/** Котировка STON.fi. units — в минимальных единицах (нанотоны / 6 знаков USDT). */
async function simulate({ offer, ask, units, slippage = '0.01' }) {
  const query = new URLSearchParams({
    offer_address: offer,
    ask_address: ask,
    units: String(units),
    slippage_tolerance: slippage,
    referral_address: SERVICE_WALLET || USDT,
    referral_fee_bps: '0',
  });
  const response = await fetch(`${STON_API}?${query}`, { method: 'POST', headers: { accept: 'application/json' } });
  const text = await response.text();
  if (!response.ok) {
    if (text.includes('not enough liquidity') || text.includes('insufficient')) {
      throw new Error('В пуле недостаточно ликвидности для такой суммы.');
    }
    throw new Error(`DEX отказал: ${text.slice(0, 120)}`);
  }
  return JSON.parse(text);
}

/** Адрес USDT-кошелька пользователя (нужен для свопа USDT → TON). */
async function usdtWalletOf(address) {
  const response = await fetch(`${TONAPI}/accounts/${encodeURIComponent(address)}/jettons/${encodeURIComponent(USDT)}`, {
    headers: { accept: 'application/json' },
  });
  if (response.status === 404) throw new Error('На этом кошельке нет USDT — обменять нечего.');
  if (!response.ok) throw new Error(`tonapi вернул ${response.status}`);
  const payload = await response.json();
  const wallet = payload?.wallet_address?.address ?? payload?.wallet_address;
  if (!wallet) throw new Error('Не удалось определить адрес USDT-кошелька.');
  return wallet;
}

/** Комиссия сервиса: 1% от суммы в TON, отдельным переводом в одном подтверждении. */
function feeMessage(nanoTon, feePercent, Address) {
  if (!SERVICE_WALLET) return null;
  const fee = (BigInt(nanoTon) * BigInt(Math.round(feePercent * 100))) / 10000n;
  if (fee < 10_000_000n) return null; // меньше 0.01 TON не отправляем
  return { address: Address.parse(SERVICE_WALLET).toString(), amount: fee.toString() };
}

/**
 * Собрать и отправить своп.
 * @param {{direction: 'ton-usdt'|'usdt-ton', amount: number, usdValue: number|null,
 *   feePercent: number, minUsd: number, maxUsd: number, rate: number|null,
 *   wallet: string|null, tonConnectUI: any}} params
 * @returns {Promise<{ok: boolean, message: string}>}
 */
export async function buildSwap(params) {
  if (!params.wallet) return { ok: false, message: 'Сначала подключите кошелёк.' };
  if (!(params.amount > 0)) return { ok: false, message: 'Введите сумму больше нуля.' };
  if (params.usdValue != null) {
    if (params.usdValue < params.minUsd) return { ok: false, message: `Минимальная сумма сделки — ${params.minUsd} $.` };
    if (params.usdValue > params.maxUsd) return { ok: false, message: `Максимальная сумма сделки — ${params.maxUsd} $.` };
  }

  const { DEX, pTON, Address } = await loadSdk();
  const provider = stubProvider();
  const slippage = '0.01';

  if (params.direction === 'ton-usdt') {
    const nanoTon = BigInt(Math.round(params.amount * 1e9));
    const sim = await simulate({ offer: PTON_MASTER, ask: USDT, units: nanoTon, slippage });
    const router = new DEX.v2_2.Router.CPI(Address.parse(sim.router_address));
    const tx = await router.getSwapTonToJettonTxParams(provider, {
      userWalletAddress: Address.parse(params.wallet),
      offerAmount: nanoTon,
      askJettonAddress: Address.parse(USDT),
      askJettonWalletAddress: Address.parse(sim.ask_jetton_wallet),
      offerJettonWalletAddress: Address.parse(sim.offer_jetton_wallet),
      minAskAmount: BigInt(sim.min_ask_units),
      queryId: Math.floor(Date.now() / 1000),
      proxyTon: new pTON.v2_1(),
    });

    const messages = [{ address: tx.to.toString(), amount: tx.value.toString(), payload: tx.body.toBoc().toString('base64') }];
    const fee = feeMessage(nanoTon, params.feePercent, Address);
    if (fee) messages.push(fee);

    await sendWithFriendlyErrors(params.tonConnectUI, {
      validUntil: Math.floor(Date.now() / 1000) + 300,
      messages,
    });
    const received = Number(sim.min_ask_units) / 1e6;
    const out = received.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
    return {
      ok: true,
      message: `Обмен отправлен. Ожидайте зачисления ≈${out} USDT на кошелёк.`,
      details: { direction: 'ton-usdt', amount: params.amount, receive: received },
    };
  }

  // USDT → TON
  const units = BigInt(Math.round(params.amount * 1e6));
  const walletAddress = await usdtWalletOf(params.wallet);
  const sim = await simulate({ offer: USDT, ask: PTON_MASTER, units, slippage });
  const router = new DEX.v2_2.Router.CPI(Address.parse(sim.router_address));
  const tx = await router.getSwapJettonToTonTxParams(provider, {
    userWalletAddress: Address.parse(params.wallet),
    offerJettonAddress: Address.parse(USDT),
    offerJettonWalletAddress: Address.parse(walletAddress),
    askJettonAddress: Address.parse(PTON_MASTER),
    askJettonWalletAddress: Address.parse(sim.ask_jetton_wallet),
    offerAmount: units,
    minAskAmount: BigInt(sim.min_ask_units),
    queryId: Math.floor(Date.now() / 1000),
    proxyTon: new pTON.v2_1(),
    gasAmount: JETTON_SWAP_VALUE,
  });

  const messages = [{ address: tx.to.toString(), amount: tx.value.toString(), payload: tx.body.toBoc().toString('base64') }];
  const fee = feeMessage(BigInt(sim.min_ask_units), params.feePercent, Address);
  if (fee) messages.push(fee);

  await sendWithFriendlyErrors(params.tonConnectUI, {
    validUntil: Math.floor(Date.now() / 1000) + 300,
    messages,
  });
  const received = Number(sim.min_ask_units) / 1e9;
  const out = received.toLocaleString('ru-RU', { maximumFractionDigits: 4 });
  return {
    ok: true,
    message: `Обмен отправлен. Ожидайте зачисления ≈${out} TON на кошелёк.`,
    details: { direction: 'usdt-ton', amount: params.amount, receive: received },
  };
}

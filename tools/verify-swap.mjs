// Проверка сборки сообщения TON → USDT (адрес пользователя берём из ответа API,
// чтобы не зависеть от валидности вписанной строки).
import { DEX, pTON } from '@ston-fi/sdk';
import { Address } from '@ton/core';

const USDT = 'EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs';
const PTON_MASTER = 'EQBnGWMCf3-FZZq1W4IWcWiGAc3PHuZ0_H-7sad2oY00o83S';

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

const qs = (p) => new URLSearchParams(p).toString();
const res = await fetch(
  `https://api.ston.fi/v1/swap/simulate?${qs({
    offer_address: PTON_MASTER,
    ask_address: USDT,
    units: '1000000000',
    slippage_tolerance: '0.01',
    referral_address: USDT,
    referral_fee_bps: '0',
  })}`,
  { method: 'POST', headers: { accept: 'application/json' } },
);
const sim = await res.json();

const router = new DEX.v2_2.Router.CPI(Address.parse(sim.router_address));
const userWallet = Address.parse(sim.ask_jetton_wallet); // валидный адрес для проверки сборки

const tx = await router.getSwapTonToJettonTxParams(provider, {
  userWalletAddress: userWallet,
  offerAmount: 1000000000n,
  askJettonAddress: Address.parse(USDT),
  askJettonWalletAddress: Address.parse(sim.ask_jetton_wallet),
  offerJettonWalletAddress: Address.parse(sim.offer_jetton_wallet),
  minAskAmount: BigInt(sim.min_ask_units),
  queryId: 42,
  proxyTon: new pTON.v2_1(),
});

console.log('курс:', sim.swap_rate, '| min_ask:', sim.min_ask_units);
console.log('to     :', tx.to.toString());
console.log('amount :', tx.value.toString(), 'nanoton');
console.log('payload:', tx.body.toBoc().toString('base64').length, 'символов base64');
console.log('preview:', tx.body.toBoc().toString('base64').slice(0, 80) + '…');

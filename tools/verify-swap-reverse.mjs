// Проверка обратного направления: USDT → TON (ask = pTON).
const USDT = 'EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs';
const PTON_MASTER = 'EQBnGWMCf3-FZZq1W4IWcWiGAc3PHuZ0_H-7sad2oY00o83S';

const qs = (p) => new URLSearchParams(p).toString();
const res = await fetch(
  `https://api.ston.fi/v1/swap/simulate?${qs({
    offer_address: USDT,
    ask_address: PTON_MASTER,
    units: '1000000',
    slippage_tolerance: '0.01',
    referral_address: USDT,
    referral_fee_bps: '0',
  })}`,
  { method: 'POST', headers: { accept: 'application/json' } },
);
const sim = await res.json();
if (!res.ok) {
  console.log('HTTP', res.status, sim);
  process.exit(1);
}
console.log('1 USDT →', (Number(sim.ask_units) / 1e9).toFixed(4), 'TON | min:', (Number(sim.min_ask_units) / 1e9).toFixed(4));
console.log('router:', sim.router_address);
console.log('ask_jetton_wallet (должен быть pTON-кошелёк роутера):', sim.ask_jetton_wallet);
console.log('offer_jetton_wallet (кошелёк USDT роутера):', sim.offer_jetton_wallet);
console.log('gas_params:', JSON.stringify(sim.gas_params));

// Сверка параметров мини-приложения (.env) и констант браузера (webapp/config.js).
//   node tools/check-webapp-config.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const projectDir = path.resolve(here, '..');

const env = fs.readFileSync(path.join(projectDir, '.env'), 'utf8');
const config = fs.readFileSync(path.join(projectDir, 'webapp', 'config.js'), 'utf8');

const envValue = (key) => new RegExp(`^${key}=(.*)$`, 'm').exec(env)?.[1]?.trim() ?? '';
const numberInJs = (key) => Number(new RegExp(`export const ${key}\\s*=\\s*([0-9.]+)`).exec(config)?.[1]);
const stringInJs = (key) => new RegExp(`export const ${key}\\s*=\\s*'([^']*)'`).exec(config)?.[1] ?? '';

let failed = 0;

for (const key of ['FEE_PERCENT', 'MIN_USD', 'MAX_USD']) {
  const fromEnv = Number(envValue(key));
  const fromJs = numberInJs(key);
  const ok = Number.isFinite(fromEnv) && Number.isFinite(fromJs) && Math.abs(fromEnv - fromJs) < 1e-9;
  console.log(`${ok ? '✓' : '✗'} ${key}: .env=${fromEnv} | webapp/config.js=${fromJs}`);
  if (!ok) failed++;
}

const envWallet = envValue('SERVICE_WALLET');
const jsWallet = stringInJs('SERVICE_WALLET');
const walletOk = envWallet === jsWallet;
console.log(`${walletOk ? '✓' : '✗'} SERVICE_WALLET: .env=${envWallet || '—'} | webapp/config.js=${jsWallet || '—'}`);
if (!walletOk) failed++;

process.exit(failed ? 1 : 0);

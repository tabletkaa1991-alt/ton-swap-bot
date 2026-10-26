// Импорт секретов из файла в .env без вывода значений в консоль + проверка ключей.
//   node tools/import-credentials.mjs "C:\path\to\.env.txt"
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const projectDir = path.resolve(here, '..');
const envPath = path.join(projectDir, '.env');
const source = process.argv[2];
if (!source) {
  console.error('укажите путь к файлу с секретами');
  process.exit(2);
}

const text = fs.readFileSync(source, 'utf8');
const token = /(\d{6,}:[A-Za-z0-9_-]{30,})/.exec(text)?.[1];
const tonapiKey = /([A-Za-z0-9]{40,})/.exec(text.replace(token ?? '', ''))?.[1];

const mask = (value) => (value ? `${value.slice(0, 4)}…${value.slice(-3)} (${value.length} симв.)` : 'НЕТ');
if (!token) console.error('✗ токен бота не найден в файле');
if (!tonapiKey) console.error('✗ ключ tonapi не найден в файле');
if (!token || !tonapiKey) process.exit(1);

const env = fs.readFileSync(envPath, 'utf8');
const setValue = (content, key, value) =>
  content.replace(new RegExp(`^${key}=.*$`, 'm'), `${key}=${value}`);

let next = env;
next = setValue(next, 'BOT_TOKEN', token);
next = setValue(next, 'TONAPI_KEY', tonapiKey);
next = setValue(next, 'NETWORK', 'mainnet');
next = setValue(next, 'FEE_PERCENT', '1.0');
next = setValue(next, 'MIN_USD', '1');
next = setValue(next, 'MAX_USD', '10');
fs.writeFileSync(envPath, next, 'utf8');
fs.chmodSync(envPath, 0o600);

console.log('записано в .env:');
console.log('  BOT_TOKEN =', mask(token));
console.log('  TONAPI_KEY =', mask(tonapiKey));

// Проверка токена бота
try {
  const response = await fetch(`https://api.telegram.org/bot${token}/getMe`);
  const payload = await response.json();
  if (payload.ok) console.log(`✓ Telegram: @${payload.result.username} (${payload.result.first_name}), can_join_groups=${payload.result.can_join_groups}`);
  else console.log(`✗ Telegram: ${payload.error_code} ${payload.description}`);
} catch (error) {
  console.log('✗ Telegram: сеть недоступна —', error.name);
}

// Проверка ключа tonapi
for (const [label, url, headers] of [
  ['tonapi (с ключом)', 'https://tonapi.io/v2/rates?tokens=ton&currencies=usd', { Authorization: `Bearer ${tonapiKey}` }],
  ['tonapi (без ключа)', 'https://tonapi.io/v2/rates?tokens=ton&currencies=usd', {}],
]) {
  try {
    const response = await fetch(url, { headers });
    const payload = await response.json();
    const price = payload?.rates?.TON?.prices?.USD;
    console.log(`${response.ok && price ? '✓' : '✗'} ${label}: HTTP ${response.status}, TON = ${price ?? '—'} USD`);
  } catch (error) {
    console.log(`✗ ${label}: сеть недоступна —`, error.name);
  }
}

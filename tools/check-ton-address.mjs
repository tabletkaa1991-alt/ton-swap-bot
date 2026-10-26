// Проверка TON-адреса без внешних зависимостей: base64url + CRC16(XMODEM).
//   node tools/check-ton-address.mjs UQ...
const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';

function base64urlDecode(text) {
  const bytes = [];
  let buffer = 0;
  let bits = 0;
  for (const char of text) {
    const value = ALPHABET.indexOf(char);
    if (value < 0) throw new Error(`недопустимый символ: ${char}`);
    buffer = (buffer << 6) | value;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      bytes.push((buffer >> bits) & 0xff);
    }
  }
  return Buffer.from(bytes);
}

function crc16(data) {
  let crc = 0;
  for (const byte of data) {
    crc ^= byte << 8;
    for (let i = 0; i < 8; i++) {
      crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
    }
  }
  return crc;
}

const address = process.argv[2];
if (!address) {
  console.error('укажите адрес');
  process.exit(2);
}

try {
  if (address.length !== 48) throw new Error(`длина ${address.length}, а нужно 48`);
  const raw = base64urlDecode(address);
  if (raw.length !== 36) throw new Error(`декодировано ${raw.length} байт вместо 36`);
  const tag = raw[0];
  const workchain = raw[1];
  const hash = raw.subarray(2, 34);
  const checksum = raw.readUInt16BE(34);
  const expected = crc16(raw.subarray(0, 34));
  if (checksum !== expected) throw new Error(`CRC не сходится: ${checksum} ≠ ${expected}`);
  const flags = [];
  // 0x40 — non-bounceable, 0x80 — testnet (так их трактует @ton/core)
  flags.push(tag & 0x40 ? 'non-bounceable' : 'bounceable');
  flags.push(tag & 0x80 ? 'testnet' : 'mainnet');
  console.log('✓ адрес валиден');
  console.log('  формат :', flags.join(', '));
  console.log('  workchain:', workchain);
  console.log('  hash    :', hash.toString('hex'));
} catch (error) {
  console.log('✗ адрес невалиден:', error.message);
  process.exit(1);
}

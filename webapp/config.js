// Параметры мини-приложения. Должны совпадать с .env:
// проверка — `node tools/check-webapp-config.mjs`.
//
// Почему дублируются: мини-приложение статика, доступа к .env у браузера нет.

export const FEE_PERCENT = 2.5; // = FEE_PERCENT в .env
export const MIN_USD = 1;       // = MIN_USD в .env
export const MAX_USD = 10;      // = MAX_USD в .env

// Кошелёк сервиса: сюда уходит комиссия отдельным переводом в TON.
// Пустая строка — комиссия не взимается.
export const SERVICE_WALLET = 'UQDPWo2iOhyhqm1DcKLsZWA2-Y5oOhV7h6N2zLNkgw-ZEdtr';

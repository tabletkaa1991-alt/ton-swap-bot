// Адаптер свопа вынесен в swap-stonfi.js: здесь только точка входа,
// чтобы app.js не зависел от конкретного DEX.
export { buildSwap } from './swap-stonfi.js';

// index.js
import createBybit from './bybit';
import createMexc from './mexc';
import createKucoin from './kucoin';
import createGateio from './gateio';
import createBinance from './binance';
import createBitget from './bitget';
import createHuobi from './huobi';
import createBingx from './bingx';
import createOurbit from './ourbit';
import createOkx from './okx';
import createHyperliquid from './hyperliquid';
import createLbank from './lbank';
import createBitmart from './bitmart';
import createAster from './aster';
import createXt from './xt';
import createCoinEx from './coinex';
import createWeex from './weex';
import createPhemex from './phemex';
import createBinanceAlpha from './binancealpha';

// Factory: createConnector(market, symbol, opts)
export function createConnector(market, symbol, opts = {}) {
  const key = (market || '').toLowerCase();
  if (key === 'bybit') return createBybit(symbol, opts);
  if (key === 'mexc') return createMexc(symbol, opts);
  if (key === 'kucoin') return createKucoin(symbol, opts);
  if (key === 'gateio') return createGateio(symbol, opts);
  if (key === 'binance') return createBinance(symbol, opts);
  if (key === 'bitget') return createBitget(symbol, opts);
  if (key === 'huobi') return createHuobi(symbol, opts);
  if (key === 'bingx') return createBingx(symbol, opts);
  if (key === 'ourbit') return createOurbit(symbol, opts);
  if (key === 'okx') return createOkx(symbol, opts);
  if (key === 'hyperliquid') return createHyperliquid(symbol, opts);
  if (key === 'lbank') return createLbank(symbol, opts);
  if (key === 'bitmart') return createBitmart(symbol, opts);
  if (key === 'aster') return createAster(symbol, opts);
  if (key === 'xt') return createXt(symbol, opts);
  if (key === 'coinex') return createCoinEx(symbol, opts);
  if (key === 'weex') return createWeex(symbol, opts);
  if (key === 'phemex') return createPhemex(symbol, opts);
  if (key === 'binancealpha') return createBinanceAlpha(symbol, opts);
  // default fallback (noop)
  return {
    connect: () => console.warn('No connector for', market),
    subscribe: () => console.warn('No subscribe for', market),
    close: () => {}
  };
}

export { default as createBybit } from './bybit';
export { default as createMexc } from './mexc';
export { default as createKucoin } from './kucoin';
export { default as createGateio } from './gateio';
export { default as createBinance } from './binance';
export { default as createBitget } from './bitget';
export { default as createHuobi } from './huobi';
export { default as createBingx } from './bingx';
export { default as createOurbit } from './bingx';
export { default as createOkx } from './okx';
export { default as createHyperliquid } from './hyperliquid';
export { default as createLbank } from './lbank';
export { default as createBitmart } from './bitmart';
export { default as createAster } from './aster';
export { default as createXt } from './xt';
export { default as createCoinEx } from './coinex';
export { default as createWeex } from './weex';
export { default as createPhemex } from './phemex';
export { default as createBinanceAlpha } from './binancealpha';

export * from './utils';

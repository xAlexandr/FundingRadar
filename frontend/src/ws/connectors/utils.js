// src/ws/connectors/utils.js
export function formatSymbolForExchange(market, symbolRaw, mode = 'futures') {
  if (!symbolRaw) return symbolRaw;
  let s = String(symbolRaw).toUpperCase().trim();

  // If user gave base only like "BTC" (no separator and no USDT/USDTM)
  const isBaseOnly = !s.includes('_') && !s.includes('-') && !s.includes('/') && !/USDTM?$/.test(s);
  switch ((market || '').toLowerCase()) {

      case 'bybit':
        // Bybit expects compact symbols like "BTCUSDT" for both futures/spot (we'll keep it simple)
        if (isBaseOnly) return `${s}USDT`;
        return s.replace(/[-_\/]/g, '');

      case 'mexc':
        // Spot uses underscore form like "BTC_USDT"
        // Futures code in Python expects keys like "BTCUSDT" (and then they replace 'USDT' -> '_USDT' when subscribing),
        // so we produce:
        if (mode === 'spot') {
          if (isBaseOnly) return `${s}_USDT`;
          // keep underscore form if exists; convert other separators
          if (s.includes('-')) return s.replace('-', '_');
          if (s.includes('/')) return s.replace('/', '_');
          if (s.includes('_')) return s;
          // if user provided "BTCUSDT" -> convert to "BTC_USDT"
          return s.replace(/USDT$/i, '_USDT');
        } else {
          // futures: use compact form like "BTCUSDT"
          if (isBaseOnly) return `${s}USDT`;
          return s.replace(/[-_\/]/g, ''); // remove separators
        }
      
    case 'ourbit':
        // Spot uses underscore form like "BTC_USDT"
        // Futures code in Python expects keys like "BTCUSDT" (and then they replace 'USDT' -> '_USDT' when subscribing),
        // so we produce:
        if (mode === 'spot') {
          if (isBaseOnly) return `${s}_USDT`;
          // keep underscore form if exists; convert other separators
          if (s.includes('-')) return s.replace('-', '_');
          if (s.includes('/')) return s.replace('/', '_');
          if (s.includes('_')) return s;
          // if user provided "BTCUSDT" -> convert to "BTC_USDT"
          return s.replace(/USDT$/i, '_USDT');
        } else {
          // futures: use compact form like "BTCUSDT"
          if (isBaseOnly) return `${s}USDT`;
          return s.replace(/[-_\/]/g, ''); // remove separators
        }
    
    case 'ourbit':
    // Spot uses underscore form like "BTC_USDT"
    // Futures code in Python expects keys like "BTCUSDT" (and then they replace 'USDT' -> '_USDT' when subscribing),
    // so we produce:
    if (mode === 'spot') {
      if (isBaseOnly) return `${s}_USDT`;
      // keep underscore form if exists; convert other separators
      if (s.includes('-')) return s.replace('-', '_');
      if (s.includes('/')) return s.replace('/', '_');
      if (s.includes('_')) return s;
      // if user provided "BTCUSDT" -> convert to "BTC_USDT"
      return s.replace(/USDT$/i, '_USDT');
    } else {
      // futures: use compact form like "BTCUSDT"
      if (isBaseOnly) return `${s}USDT`;
      return s.replace(/[-_\/]/g, ''); // remove separators
    }

    case 'okx':
      // Spot uses underscore form like "BTC_USDT"
      // Futures code in Python expects keys like "BTCUSDT" (and then they replace 'USDT' -> '_USDT' when subscribing),
      // so we produce:
      if (mode === 'spot') {
        if (isBaseOnly) return `${s}_USDT`;
        // keep underscore form if exists; convert other separators
        if (s.includes('-')) return s.replace('-', '_');
        if (s.includes('/')) return s.replace('/', '_');
        if (s.includes('_')) return s;
        // if user provided "BTCUSDT" -> convert to "BTC_USDT"
        return s.replace(/USDT$/i, '_USDT');
      } else {
        // futures: use compact form like "BTCUSDT"
        if (isBaseOnly) return `${s}USDT`;
        return s.replace(/[-_\/]/g, ''); // remove separators
      }

    case 'kucoin':
      if (isBaseOnly) {
        // spot -> "BTC-USDT", futures -> "BTCUSDTM" (matches your Python)
        return mode === 'spot' ? `${s}-USDT` : `${s}USDTM`;
      }
      // already looks like pair
      if (mode === 'spot') {
        if (s.includes('/')) return s.replace('/', '-');
        if (s.includes('_')) return s.replace('_', '-');
        return s;
      } else {
        // futures: remove dashes/slashes
        return s.replace(/[-/]/g, '');
      }

    case 'binance':
      if (isBaseOnly) return `${s}USDT`;
      return s.replace(/[-_\/]/g, '');

    case 'gateio':
      if (isBaseOnly) return `${s}_USDT`;
      // keep underscore form if exists, otherwise convert separators to underscore
      if (s.includes('-')) return s.replace('-', '_');
      if (s.includes('/')) return s.replace('/', '_');
      return s;
    
    case 'bitget':
      // Bitget expects compact symbols like "BTCUSDT" for both spot and futures (no separators)
      if (isBaseOnly) return `${s}USDT`;
      return s.replace(/[-_\/]/g, '');
    
    case 'huobi':
      // Huobi expects compact symbols like "BTCUSDT" (we keep uppercase; connector will lowercase when building topic)
      if (isBaseOnly) return `${s}USDT`;
      return s.replace(/[-_\/]/g, '');

    case 'bingx':
      // BingX uses compact symbols like BTCUSDT for internal formatting,
      // but channels expect dash before USDT (we convert when building channel).
      if (isBaseOnly) return `${s}USDT`;
      return s.replace(/[-_\/]/g, '');

    case 'hyperliquid':
      // Spot uses underscore form like "BTC_USDT"
      // Futures code in Python expects keys like "BTCUSDT" (and then they replace 'USDT' -> '_USDT' when subscribing),
      // so we produce:
      if (mode === 'futures') {
        // futures: use compact form like "BTCUSDT"
        if (isBaseOnly) return `${s}USDT`;
        return s.replace(/[-_\/]/g, ''); // remove separators
      } 
    
    case 'aster':
      // Spot: compact form like "BTCUSDT"
      // Futures: compact form like "BTCUSDT"
      if (isBaseOnly) return `${s}USDT`;
      return s.replace(/[-_\/]/g, '');

    case 'lbank':
      // Huobi expects compact symbols like "BTCUSDT" (we keep uppercase; connector will lowercase when building topic)
      if (isBaseOnly) return `${s}USDT`;
      return s.replace(/[-_\/]/g, '');
    
    case 'xt':
  
      if (isBaseOnly) return `${s}_USDT`;
      if (s.includes('-')) return s.replace('-', '_');
      if (s.includes('/')) return s.replace('/', '_');
      if (s.includes('_')) return s;
      return s.replace(/USDT$/i, '_USDT');

    case 'coinex':
      if (isBaseOnly) return `${s}USDT`;
      return s.replace(/[-_\/]/g, '');

    // ---------- в formatSymbolForExchange ----------
    case 'weex':
      // WEEX использует компактные символы (BTCUSDT) как для фьючерсов, так и для спота
      if (isBaseOnly) return `${s}USDT`;
      return s.replace(/[-_\/]/g, '');

    case 'phemex':
      if (mode === 'spot') {
        // Спот: символы с префиксом 's' (например, sBTCUSDT)
        if (isBaseOnly) return `s${s}USDT`;
        if (!s.startsWith('s')) return `s${s}`;
        return s;
      } else {
        // Фьючерсы: компактные символы без префикса
        if (isBaseOnly) return `${s}USDT`;
        return s.replace(/[-_\/]/g, '');
      }

    case 'binancealpha':
      // BinanceAlpha is spot-only, uses compact symbols like BTCUSDT
      if (isBaseOnly) return `${s}USDT`;
      return s.replace(/[-_\/]/g, '');

    default:
      // default: append USDT if base only
      if (isBaseOnly) return `${s}USDT`;
      return s;
  }
}

/**
 * buildSubscribePayload(market, symbolFormatted, mode)
 * returns { subscribePayload, unsubPayload, topic }
 * symbolFormatted must already be full pair (use formatSymbolForExchange)
 */
export function buildSubscribePayload(market, symbolFormatted, mode = 'futures') {
  const m = (market || '').toLowerCase();

    if (m === 'mexc') {
      if (mode === 'spot') {
        // expects symbolFormatted like "BTC_USDT"
        // Python uses: params: [ `spot@public.limit.depth.v3.api.pb@${k}@20` ]
        const paramStr = `spot@public.limit.depth.v3.api.pb@${symbolFormatted.replace('_', '')}@20`;
        const payload = { method: 'SUBSCRIPTION', params: [paramStr] };
        const unsub  = { method: 'UNSUBSCRIPTION', params: [paramStr] };
        return { subscribePayload: payload, unsubPayload: unsub, topic: paramStr };
      } else {
        // futures: expects param symbol like "BTC_USDT" (they do replace('USDT','_USDT'))
        // we will produce param.symbol with underscore (so caller should pass "BTCUSDT" -> we convert earlier)
        const payload = { method: 'sub.depth.full', param: { symbol: symbolFormatted.replace(/USDT$/, '_USDT'), limit: '20' } };
        // best-effort unsub (python doesn't use unsub for futures, but return something sensible)
        const unsub = { method: 'unsub.depth.full', param: { symbol: symbolFormatted.replace(/USDT$/, '_USDT') } };
        return { subscribePayload: payload, unsubPayload: unsub, topic: payload.param.symbol };
      }
    }

    if (m === 'ourbit') {
      if (mode === 'spot') {
        // expects symbolFormatted like "BTC_USDT"
        // Python uses: params: [ `spot@public.limit.depth.v3.api.pb@${k}@20` ]
        const paramStr = `spot@public.limit.depth.v3.api@${symbolFormatted.replace('_', '')}@20`;
        const payload = { method: 'SUBSCRIPTION', params: [paramStr] };
        const unsub  = { method: 'UNSUBSCRIPTION', params: [paramStr] };
        return { subscribePayload: payload, unsubPayload: unsub, topic: paramStr };
      } else {
        // futures: expects param symbol like "BTC_USDT" (they do replace('USDT','_USDT'))
        // we will produce param.symbol with underscore (so caller should pass "BTCUSDT" -> we convert earlier)
        const payload = { method: 'sub.depth.full', param: { symbol: symbolFormatted.replace(/USDT$/, '_USDT'), limit: '20' } };
        // best-effort unsub (python doesn't use unsub for futures, but return something sensible)
        const unsub = { method: 'unsub.depth.full', param: { symbol: symbolFormatted.replace(/USDT$/, '_USDT') } };
        return { subscribePayload: payload, unsubPayload: unsub, topic: payload.param.symbol };
      }
    }
    
    if (m === 'bitmart') {
      if (mode === 'spot') {
        // expects symbolFormatted like "BTC_USDT"
        // Python uses: params: [ `spot@public.limit.depth.v3.api.pb@${k}@20` ]
        const payload = { op: 'subscribe', args: [`spot/depth20:${symbolFormatted.replace(/USDT$/, '_USDT')}`] };
        const unsub  = { op: 'unsubscribe', args: [`spot/depth20:${symbolFormatted.replace(/USDT$/, '_USDT')}`] };
        return { subscribePayload: payload, unsubPayload: unsub, topic: symbolFormatted.replace(/USDT$/, '_USDT') };
      } else {
        // futures: expects param symbol like "BTC_USDT" (they do replace('USDT','_USDT'))
        // we will produce param.symbol with underscore (so caller should pass "BTCUSDT" -> we convert earlier)
        const payload = { action: 'subscribe', args: [`futures/depth50:${symbolFormatted.replace('_', '')}`] };
        // best-effort unsub (python doesn't use unsub for futures, but return something sensible)
        const unsub = { action: 'unsubscribe', args: [`futures/depth50:${symbolFormatted.replace('_', '')}`] };
        return { subscribePayload: payload, unsubPayload: unsub, topic: symbolFormatted.replace('_', '') };
      }
    }

    if (m === 'okx') {
      if (mode === 'spot') {
        // expects symbolFormatted like "BTC_USDT"
        // Python uses: params: [ `spot@public.limit.depth.v3.api.pb@${k}@20` ]
        const payload = { op: 'subscribe', args: [{channel: "books5", instType: "SPOT", instId: `${symbolFormatted.replace('_', '-')}`}] };
        const unsub  = { method: 'unsubscribe', args: [{channel: "books5", instType: "SPOT", instId: `${symbolFormatted.replace('_', '-')}`}] };
        return { subscribePayload: payload, unsubPayload: unsub, topic: payload.args[0].instId };
      } else {
        // futures: expects param symbol like "BTC_USDT" (they do replace('USDT','_USDT'))
        // we will produce param.symbol with underscore (so caller should pass "BTCUSDT" -> we convert earlier)
        const payload = { op: 'subscribe', args: [{channel: "books5", instType: "SWAP", instId: `${symbolFormatted.replace('USDT', '-USDT-SWAP')}`}] };
        // best-effort unsub (python doesn't use unsub for futures, but return something sensible)
        const unsub = { op: 'unsubscribe', args: [{channel: "books5", instType: "SWAP", instId: `${symbolFormatted.replace('USDT', '-USDT-SWAP')}`}] };
        return { subscribePayload: payload, unsubPayload: unsub, topic: payload.args[0].instId };
      }
    }

  if (m === 'kucoin') {
    const topic = (mode === 'spot')
      ? `/spotMarket/level2Depth50:${symbolFormatted}`   // "BTC-USDT"
      : `/contractMarket/level2Depth50:${symbolFormatted}`; // "BTCUSDTM" or "BTCUSDT"
    const payload = { id: String(Math.floor(Math.random() * 1e9)), type: 'subscribe', topic, privateChannel: false, response: true };
    const unsub   = { id: String(Math.floor(Math.random() * 1e9)), type: 'unsubscribe', topic };
    return { subscribePayload: payload, unsubPayload: unsub, topic };
  }

  if (m === 'binance') {
    const topicStr = `${String(symbolFormatted).toLowerCase()}@depth20@100ms`;
    const id = Math.floor(Math.random() * 1e9);
    return { subscribePayload: { method: 'SUBSCRIBE', params: [topicStr], id }, unsubPayload: { method: 'UNSUBSCRIBE', params: [topicStr], id: id + 1 }, topic: topicStr };
  }
  

  if (m === 'gateio') {
    // symbolFormatted expected like "FLOW_USDT" or "BTC_USDT"
    if (mode === 'spot') {
      const payload = { channel: 'spot.order_book', event: 'subscribe', payload: [symbolFormatted, '50', '100ms'] };
      const unsub   = { channel: 'spot.order_book', event: 'unsubscribe', payload: [symbolFormatted] };
      return { subscribePayload: payload, unsubPayload: unsub, topic: 'spot.order_book' };
    } else {
      const payload = { channel: 'futures.order_book', event: 'subscribe', payload: [symbolFormatted, '50', '0'] };
      const unsub   = { channel: 'futures.order_book', event: 'unsubscribe', payload: [symbolFormatted] };
      return { subscribePayload: payload, unsubPayload: unsub, topic: 'futures.order_book' };
    }
  }

  if (m === 'hyperliquid') {
      if (mode === 'futures') {
        // expects symbolFormatted like "BTC_USDT"
        // Python uses: params: [ `spot@public.limit.depth.v3.api.pb@${k}@20` ]
        const payload = { method: 'subscribe', subscription: {type: "l2Book", coin: `${symbolFormatted.replace('_USDT', '')}`} };
        const unsub  = { method: 'unsubscribe', subscription: {type: "l2Book", coin: `${symbolFormatted.replace('_USDT', '')}`} };
        return { subscribePayload: payload, unsubPayload: unsub, topic: payload.subscription.coin };
      }
  }
  if (m === 'aster') {
      // Spot: sstream.asterdex.com, depth20 stream
      if (mode === 'spot') {
        const paramStr = `${symbolFormatted.replace('_', '').toLowerCase()}usdt@depth20`;
        const payload = { method: 'SUBSCRIBE', params: [paramStr], id: String(Math.floor(Math.random() * 1e9)) };
        const unsub  = { method: 'UNSUBSCRIBE', params: [paramStr], id: String(Math.floor(Math.random() * 1e9)) };
        return { subscribePayload: payload, unsubPayload: unsub, topic: paramStr };
      }
      // Futures: fstream.asterdex.com, depth20@100ms stream
      if (mode === 'futures') {
        let id_sub = String(Math.floor(Math.random() * 1e9));
        const paramStr = `${symbolFormatted.replace('_', '').toLowerCase()}usdt@depth20@100ms`;
        const payload = { method: 'SUBSCRIBE', params: [paramStr], id: id_sub };
        const unsub  = { method: 'UNSUBSCRIBE', params: [paramStr], id: id_sub };
        return { subscribePayload: payload, unsubPayload: unsub, topic: symbolFormatted.replace('_', '').toLowerCase() + 'usdt' };
      } 
    }
  
    if (m === 'xt') {

  if (mode === 'spot') {
    const topic = `depth@${symbolFormatted.toLowerCase()},50`;
    return {
      subscribePayload: {
        method: "subscribe",
        params: [topic],
        id: String(Math.floor(Math.random() * 1e9))
      },
      unsubPayload: {
        method: "unsubscribe",
        params: [topic],
        id: String(Math.floor(Math.random() * 1e9))
      },
      topic
    };
  }

  // futures
  const topic = `depth@${symbolFormatted.toLowerCase()},50,100ms`;
  return {
    subscribePayload: {
      method: "SUBSCRIBE",
      params: [topic],
      id: String(Math.floor(Math.random() * 1e9))
    },
    unsubPayload: {
      method: "UNSUBSCRIBE",
      params: [topic],
      id: String(Math.floor(Math.random() * 1e9))
    },
    topic
  };
}

if (m === 'coinex') {
  const limit = 50; // можно параметризовать через opts.limit
  const id = Math.floor(Math.random() * 1e9);
  const subscribePayload = {
    method: 'depth.subscribe',
    params: {
      market_list: [
        [symbolFormatted, limit, "0", true]   // формат: [symbol, limit, "0", full]
      ]
    },
    id
  };
  const unsubPayload = {
    method: 'depth.unsubscribe',
    params: {
      market_list: [
        [symbolFormatted, limit, "0", true]
      ]
    },
    id: id + 1
  };
  return { subscribePayload, unsubPayload, topic: symbolFormatted };
}

if (m === 'weex') {
  // Формат подписки как у Binance: метод SUBSCRIBE, канал depth@symbol@50
  const topic = `${symbolFormatted}@depth15`;
  const id = Math.floor(Math.random() * 1e9);
  const payload = { method: 'SUBSCRIBE', params: [topic], id };
  const unsub   = { method: 'UNSUBSCRIBE', params: [topic], id: id + 1 };
  return { subscribePayload: payload, unsubPayload: unsub, topic };
}

  if (m === 'phemex') {
    const id = Math.floor(Math.random() * 1e9);
    if (mode === 'spot') {
      // Спот: orderbook.subscribe, полная глубина
      const params = [symbolFormatted, false];
      const subscribePayload = { id, method: 'orderbook.subscribe', params };
      const unsubPayload = { id: id + 1, method: 'orderbook.unsubscribe', params: [symbolFormatted] };
      return { subscribePayload, unsubPayload, topic: symbolFormatted };
    } else {
      // Фьючерсы: orderbook_p.subscribe, глубина 30 (можно параметризовать)
      const depth = 30;
      const params = [symbolFormatted, false, depth];
      const subscribePayload = { id, method: 'orderbook_p.subscribe', params };
      const unsubPayload = { id: id + 1, method: 'orderbook_p.unsubscribe', params: [symbolFormatted] };
      return { subscribePayload, unsubPayload, topic: symbolFormatted };
    }
  }



  return { subscribePayload: null, unsubPayload: null, topic: null };
}

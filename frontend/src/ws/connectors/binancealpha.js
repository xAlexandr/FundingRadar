// src/ws/connectors/binancealpha.js
// BinanceAlpha connector — WebSocket depth stream.
// WebSocket: wss://nbstream.binance.com/w3w/wsa/stream
// Primary: <alphaId_usdt>@depth20@500ms (20 levels, UI orders)
// Fallback: <alphaId_usdt>@fulldepth@100ms (all orders, fewer levels)
//
// If alphaId is not provided in opts, resolves it from REST API on connect.

import { formatSymbolForExchange } from './utils';

const WS_ENDPOINT = 'wss://nbstream.binance.com/w3w/wsa/stream';
const REST_API = 'https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list';

export default function createBinanceAlpha(symbolRaw, opts = {}) {
  const mode = opts.mode || 'spot';
  const name_market = 'BinanceAlpha';
  const symbolFormatted = opts.symbolOverride
    ? opts.symbolOverride
    : formatSymbolForExchange('binancealpha', symbolRaw, mode);
  const symbolOut = symbolFormatted;

  const baseSymbol = symbolOut.replace(/USDT$/i, '').toUpperCase();

  let alphaId = opts.alphaId || '';

  // Build stream names
  function buildStreams(aid) {
    if (!aid) return { primary: '', fallback: '' };
    const ws = aid.toLowerCase() + 'usdt';
    return {
      primary: `${ws}@depth20@500ms`,
      fallback: `${ws}@fulldepth@500ms`,
    };
  }

  let streams = buildStreams(alphaId);
  let activeStream = streams.primary; // currently subscribed stream

  // Options
  const WATCHDOG_TIMEOUT_MS = typeof opts.watchdogTimeoutMs === 'number' ? opts.watchdogTimeoutMs : 20000;
  const IDLE_CHECK_MS = typeof opts.watchdogCheckMs === 'number' ? opts.watchdogCheckMs : 5000;
  const CONNECT_TIMEOUT_MS = typeof opts.connectTimeoutMs === 'number' ? opts.connectTimeoutMs : 30000;
  const BASE_BACKOFF_MS = typeof opts.baseBackoffMs === 'number' ? opts.baseBackoffMs : 1000;
  const MAX_BACKOFF_MS = typeof opts.maxBackoffMs === 'number' ? opts.maxBackoffMs : 30000;
  const MAX_RECONNECT_ATTEMPTS = typeof opts.maxReconnectAttempts === 'number' ? opts.maxReconnectAttempts : null;
  const PING_INTERVAL_MS = 15000;
  const FALLBACK_TIMEOUT_MS = 15000; // wait 3s for depth20 data before fallback

  // State
  let socket = null;
  let onData = null;
  let isSubscribed = false;

  let lastMessageAt = 0;
  let watchdogInterval = null;

  let reconnectTimer = null;
  let reconnectAttempts = 0;
  let manualClose = false;
  let connecting = false;
  let lastConnectAttempt = 0;

  let pingInterval = null;
  let fallbackTimer = null;

  let connId = 0;
  let activeConnId = 0;

  // Orderbook state
  let bidsMap = new Map();
  let asksMap = new Map();
  let hasSnapshot = false;
  let useFallback = false;

  // -----------------------
  // Resolve alphaId from REST API
  // -----------------------

  async function resolveAlphaId() {
    if (alphaId) return alphaId;
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 8000);
      const response = await fetch(REST_API, {
        signal: controller.signal,
        headers: { 'Accept': 'application/json' },
      });
      clearTimeout(timeoutId);
      if (!response.ok) return '';
      const data = await response.json();
      if (!data?.data) return '';
      const token = data.data.find(t => (t.symbol || '').toUpperCase() === baseSymbol);
      if (token?.alphaId) {
        alphaId = token.alphaId;
        streams = buildStreams(alphaId);
        activeStream = streams.primary;
        console.info(`[${name_market}] Resolved alphaId: ${alphaId} for ${baseSymbol}`);
        return alphaId;
      }
      return '';
    } catch (e) {
      console.error(`[${name_market}] Failed to resolve alphaId:`, e.message);
      return '';
    }
  }

  // -----------------------
  // Orderbook helpers
  // -----------------------

  function resetBook() {
    bidsMap.clear();
    asksMap.clear();
    hasSnapshot = false;
  }

  function applySnapshot(data) {
    if (!data) return;
    const rawB = data.b || [];
    const rawA = data.a || [];

    // First snapshot with data: replace entire book
    // Empty snapshot: skip (preserve previous state)
    // Subsequent: merge
    if (!hasSnapshot && (rawB.length > 0 || rawA.length > 0)) {
      bidsMap.clear();
      asksMap.clear();
      hasSnapshot = true;
    }

    // Update bids from snapshot
    if (rawB.length > 0) {
      for (const item of rawB) {
        if (!Array.isArray(item)) continue;
        const p = String(item[0]);
        const s = parseFloat(item[1]);
        if (s > 0) bidsMap.set(p, s);
        else bidsMap.delete(p);
      }
    }

    // Update asks from snapshot
    if (rawA.length > 0) {
      for (const item of rawA) {
        if (!Array.isArray(item)) continue;
        const p = String(item[0]);
        const s = parseFloat(item[1]);
        if (s > 0) asksMap.set(p, s);
        else asksMap.delete(p);
      }
    }
    hasSnapshot = true;
  }

  function mapToSortedArrays() {
    const bids = Array.from(bidsMap.entries())
      .map(([p, s]) => [parseFloat(p), parseFloat(s)])
      .filter(Boolean)
      .sort((a, b) => b[0] - a[0]);

    const asks = Array.from(asksMap.entries())
      .map(([p, s]) => [parseFloat(p), parseFloat(s)])
      .filter(Boolean)
      .sort((a, b) => a[0] - b[0]);

    return { bids, asks };
  }

  function emitData(raw, stream) {
    if (!onData) return;
    const { asks, bids } = mapToSortedArrays();
    if (!asks.length && !bids.length) return;
    try {
      onData({
        market: name_market,
        symbol: symbolOut,
        asks,
        bids,
        raw,
        topic: stream,
        timestamp: Date.now(),
      });
    } catch (e) {
      console.error(`[${name_market}] onData error`, e);
    }
  }

  // -----------------------
  // Timer helpers
  // -----------------------

  function clearWatchdog() {
    if (watchdogInterval) { clearInterval(watchdogInterval); watchdogInterval = null; }
  }

  function startWatchdog(thisConnId) {
    clearWatchdog();
    lastMessageAt = Date.now();
    watchdogInterval = setInterval(() => {
      try {
        if (thisConnId !== activeConnId) return clearWatchdog();
        if (manualClose || !socket) return;
        if (Date.now() - lastMessageAt > WATCHDOG_TIMEOUT_MS) {
          console.warn(`[${name_market}] watchdog: no messages — reconnecting`);
          forceReconnectImmediate('watchdog');
        }
      } catch (e) {}
    }, IDLE_CHECK_MS);
  }

  function clearPing() {
    if (pingInterval) { clearInterval(pingInterval); pingInterval = null; }
  }

  function clearReconnect() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  }

  function clearFallback() {
    if (fallbackTimer) { clearTimeout(fallbackTimer); fallbackTimer = null; }
  }

  function scheduleReconnect(delay = BASE_BACKOFF_MS) {
    if (manualClose || reconnectTimer || connecting) return;
    if (socket && (socket.readyState === WebSocket.CONNECTING || socket.readyState === WebSocket.OPEN)) return;
    if (MAX_RECONNECT_ATTEMPTS !== null && reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) return;

    const scheduledFor = activeConnId;
    const backoff = Math.min(MAX_BACKOFF_MS, Math.pow(2, reconnectAttempts) * delay);
    const jitter = Math.floor(Math.random() * 500);
    reconnectAttempts += 1;
    reconnectTimer = setTimeout(() => {
      if (scheduledFor !== activeConnId) { reconnectTimer = null; return; }
      reconnectTimer = null;
      doConnect();
    }, Math.max(200, backoff + jitter));
  }

  function sendSafe(obj) {
    try {
      if (!socket || socket.readyState !== WebSocket.OPEN) return false;
      socket.send(JSON.stringify(obj));
      return true;
    } catch (e) { return false; }
  }

  // -----------------------
  // Switch stream (depth20 → fulldepth)
  // -----------------------

  function switchToFallback() {
    if (useFallback || manualClose) return;
    useFallback = true;
    activeStream = streams.fallback;
    console.info(`[${name_market}] Switching to fallback: ${streams.fallback}`);

    // Unsubscribe from primary, subscribe to fallback
    if (socket?.readyState === WebSocket.OPEN) {
      sendSafe({ method: 'UNSUBSCRIBE', params: [streams.primary], id: Date.now() });
      sendSafe({ method: 'SUBSCRIBE', params: [streams.fallback], id: Date.now() + 1 });
    }
  }

  // -----------------------
  // Force reconnect
  // -----------------------

  function forceReconnectImmediate() {
    if (manualClose) return;
    clearReconnect();
    clearFallback();
    connId += 1;
    activeConnId = connId;

    if (socket?.readyState === WebSocket.OPEN) {
      try { sendSafe({ method: 'UNSUBSCRIBE', params: [activeStream], id: Date.now() }); } catch (e) {}
    }
    try { if (socket) { socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null; socket.close(); } } catch (e) {}
    clearPing();
    clearWatchdog();
    socket = null;
    isSubscribed = false;
    connecting = false;
    useFallback = false;
    activeStream = streams.primary;

    setTimeout(() => { try { doConnect(); } catch (e) { scheduleReconnect(); } }, 50);
  }

  // -----------------------
  // Core connect
  // -----------------------

  function doConnect() {
    if (!streams.primary) return;
    try {
      if (connecting) return;
      const now = Date.now();
      if (now - lastConnectAttempt < 400) { scheduleReconnect(500); return; }
      lastConnectAttempt = now;
      manualClose = false;
      connecting = true;

      connId += 1;
      const thisConnId = connId;
      activeConnId = thisConnId;

      if (socket) {
        try { socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null; } catch (e) {}
        try { socket.close(); } catch (e) {}
        socket = null;
      }

      const ws = new WebSocket(WS_ENDPOINT);
      socket = ws;

      const connectTimeout = setTimeout(() => {
        if (thisConnId !== activeConnId) return;
        if (ws?.readyState === WebSocket.CONNECTING) try { ws.close(); } catch (e) {}
      }, CONNECT_TIMEOUT_MS);

      ws.onopen = () => {
        if (thisConnId !== activeConnId) return;
        clearTimeout(connectTimeout);
        reconnectAttempts = 0;
        connecting = false;
        lastMessageAt = Date.now();
        startWatchdog(thisConnId);

        // Subscribe to primary stream
        const stream = useFallback ? streams.fallback : streams.primary;
        activeStream = stream;
        sendSafe({ method: 'SUBSCRIBE', params: [stream], id: 1 });
        isSubscribed = true;

        // Start fallback timer: if no depth20 data in 3s, switch to fulldepth
        if (!useFallback && streams.fallback) {
          clearFallback();
          fallbackTimer = setTimeout(() => {
            if (!hasSnapshot && !useFallback && !manualClose) {
              switchToFallback();
            }
          }, FALLBACK_TIMEOUT_MS);
        }

        clearPing();
        pingInterval = setInterval(() => {
          if (thisConnId !== activeConnId) return;
          sendSafe({ method: 'PING', id: Date.now() });
        }, PING_INTERVAL_MS);
      };

      ws.onmessage = (ev) => {
        if (thisConnId !== activeConnId) return;
        lastMessageAt = Date.now();

        let text;
        if (typeof ev.data === 'string') text = ev.data;
        else if (ev.data instanceof ArrayBuffer) text = new TextDecoder().decode(new Uint8Array(ev.data));
        else if (ev.data instanceof Blob) { ev.data.text().then(t => processMessage(t)); return; }
        else return;

        processMessage(text);
      };

      ws.onclose = (ev) => {
        if (thisConnId !== activeConnId) return;
        isSubscribed = false;
        clearPing();
        clearWatchdog();
        clearFallback();
        connecting = false;
        useFallback = false;
        activeStream = streams.primary;
        if (!manualClose) scheduleReconnect();
      };

      ws.onerror = () => {};
    } catch (e) {
      connecting = false;
      scheduleReconnect();
    }
  }

  // -----------------------
  // Message processing
  // -----------------------

  function processMessage(text) {
    if (!text) return;
    let msg;
    try { msg = JSON.parse(text); } catch { return; }

    if (msg.result === null) return; // sub/unsub confirmation

    const stream = msg.stream || '';
    if (!stream.includes('depth') && !stream.includes('fulldepth')) return;

    const data = msg.data;
    if (!data) return;

    try {
      applySnapshot(data);

      // Got data from primary — cancel fallback timer
      if (!useFallback && hasSnapshot) {
        clearFallback();
      }

      emitData(msg, stream);
    } catch (e) {
      console.error(`[${name_market}] processMessage error`, e);
    }
  }

  // -----------------------
  // Public connect
  // -----------------------

  async function connect() {
    if (!streams.primary) {
      await resolveAlphaId();
    }
    if (!streams.primary) {
      console.warn(`[${name_market}] Cannot connect: no alphaId for ${baseSymbol}`);
      return;
    }
    doConnect();
  }

  // -----------------------
  // Public API
  // -----------------------

  function subscribe(cb) {
    onData = cb;
    connect();
    return () => {
      manualClose = true;
      connId += 1;
      activeConnId = connId;
      clearFallback();
      if (socket?.readyState === WebSocket.OPEN) {
        sendSafe({ method: 'UNSUBSCRIBE', params: [activeStream], id: Date.now() });
      }
      try { if (socket) { socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null; socket.close(); } } catch (e) {}
      socket = null;
      isSubscribed = false;
      useFallback = false;
      activeStream = streams.primary;
      clearPing();
      clearWatchdog();
      clearReconnect();
    };
  }

  function close() {
    manualClose = true;
    connId += 1;
    activeConnId = connId;
    clearFallback();
    try { if (socket) { socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null; socket.close(); } } catch (e) {}
    socket = null;
    isSubscribed = false;
    useFallback = false;
    clearPing();
    clearWatchdog();
    clearReconnect();
  }

  return { connect: () => connect(), subscribe, close };
}

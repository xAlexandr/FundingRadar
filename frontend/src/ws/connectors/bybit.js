// src/ws/connectors/bybit.js
import { buildSubscribePayload, formatSymbolForExchange } from './utils';

// Improved createAster: keeps your payload building + message parsing 1:1,
// but makes reconnects *immediate* by abandoning previous socket quickly
// (stale-event protection via connection id), and prevents multiple overlapping
// reconnect attempts / watchdog storms.

export default function createBybit(symbolRaw, opts = {}) {
  const mode = opts.mode || 'spot';
  const name_market = 'Bybit';
  const endpoint = (mode === 'spot') ? 'wss://stream.bybit.com/v5/public/spot' : 'wss://stream.bybit.com/v5/public/linear';
  const symbolFormatted = opts.symbolOverride || formatSymbolForExchange(`${name_market.toLowerCase()}`, symbolRaw, mode);
  const symbolOut = symbolFormatted;
  // -----------------------
  // Configurable options
  // -----------------------
  const WATCHDOG_TIMEOUT_MS = typeof opts.watchdogTimeoutMs === 'number' ? opts.watchdogTimeoutMs : 10000;
  const IDLE_CHECK_MS = typeof opts.watchdogCheckMs === 'number' ? opts.watchdogCheckMs : 5000;
  const CONNECT_TIMEOUT_MS = typeof opts.connectTimeoutMs === 'number' ? opts.connectTimeoutMs : 15000;
  const BASE_BACKOFF_MS = typeof opts.baseBackoffMs === 'number' ? opts.baseBackoffMs : 1000;
  const MAX_BACKOFF_MS = typeof opts.maxBackoffMs === 'number' ? opts.maxBackoffMs : 30000;
  const MAX_RECONNECT_ATTEMPTS = typeof opts.maxReconnectAttempts === 'number' ? opts.maxReconnectAttempts : null;
  const PING_INTERVAL_MS = 20000; // 10s, поменяй на своё значение или оставь
  // -----------------------
  // State
  // -----------------------
  let socket = null;
  let onData = null;
  let isSubscribed = false;

  // watchdog only (removed idle timer)
  let lastMessageAt = 0;
  let watchdogInterval = null;

  // reconnect / backoff
  let reconnectTimer = null;
  let reconnectAttempts = 0;
  let manualClose = false;
  let connecting = false;
  let lastConnectAttempt = 0;

  // ping
  let pingInterval = null;

  // connection id — increments whenever we start a new connection; used to ignore events from stale sockets
  let connId = 0; // ever-increasing
  let activeConnId = 0; // id of current active socket

  // Local orderbook state for snapshot/delta processing
  let bidsMap = new Map(); // price(str) -> size(number)
  let asksMap = new Map();
  let hasSnapshot = false;
  let lastSeq = null;

 // const sendPingNow = null;
  // НЕ УДАЛЯТЬ КАК ПРИМЕР ПИНГА
    function sendPingNow() {
      const pingMethod = { op: 'ping' };
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      try {
      socket.send(JSON.stringify(pingMethod)); // <- поменяй строку на ожидаемую (например: '2')
      // Если считаешь отправку пинга достаточной активностью — раскомментируй:
      // lastMessageAt = Date.now();
      } catch (e) { /* ignore */ }
  }
  
  // -----------------------
  // Helpers
  // -----------------------
  function resetLocalBook() {
    bidsMap = new Map();
    asksMap = new Map();
    hasSnapshot = false;
    lastSeq = null;
  }

  function mapToSortedArrays() {
    const bids = Array.from(bidsMap.entries())
      .map(([p, s]) => [parseFloat(p), parseFloat(s)])
      .filter(Boolean)
      .sort((a, b) => b[0] - a[0]); // descending

    const asks = Array.from(asksMap.entries())
      .map(([p, s]) => [parseFloat(p), parseFloat(s)])
      .filter(Boolean)
      .sort((a, b) => a[0] - b[0]); // ascending

    return { bids, asks };
  }

  function applySnapshot(data) {
    resetLocalBook();
    if (!data) return;
    const rawB = data.b || [];
    const rawA = data.a || [];

    for (const item of rawB) {
      if (!Array.isArray(item)) continue;
      const p = String(item[0]);
      const s = parseFloat(item[1]);
      if (s && s > 0) bidsMap.set(p, s);
    }
    for (const item of rawA) {
      if (!Array.isArray(item)) continue;
      const p = String(item[0]);
      const s = parseFloat(item[1]);
      if (s && s > 0) asksMap.set(p, s);
    }

    hasSnapshot = true;
    lastSeq = data.seq ?? data.u ?? lastSeq;
  }

  function applyDelta(data) {
    if (!data) return;
    // We require a snapshot first
    if (!hasSnapshot) return;

    const seq = data.seq ?? data.u ?? null;
    // If seq is present and less or equal to lastSeq, ignore (old)
    if (seq !== null && lastSeq !== null && seq <= lastSeq) {
      return;
    }

    const rawB = data.b || [];
    const rawA = data.a || [];

    for (const item of rawB) {
      if (!Array.isArray(item)) continue;
      const p = String(item[0]);
      const s = parseFloat(item[1]);
      if (!Number.isFinite(s)) continue;
      if (s === 0) {
        bidsMap.delete(p);
      } else {
        bidsMap.set(p, s);
      }
    }

    for (const item of rawA) {
      if (!Array.isArray(item)) continue;
      const p = String(item[0]);
      const s = parseFloat(item[1]);
      if (!Number.isFinite(s)) continue;
      if (s === 0) {
        asksMap.delete(p);
      } else {
        asksMap.set(p, s);
      }
    }

    if (seq !== null) lastSeq = seq;
  }

  function clearWatchdog() {
    if (watchdogInterval) { clearInterval(watchdogInterval); watchdogInterval = null; }
  }

  function startWatchdog(thisConnId) {
    // single watchdog per current socket
    clearWatchdog();
    lastMessageAt = Date.now();
    watchdogInterval = setInterval(() => {
      try {
        // ignore if this watchdog is for stale connection
        if (thisConnId !== activeConnId) return clearWatchdog();
        if (manualClose) return;
        if (!socket) return;
        const delta = Date.now() - (lastMessageAt || 0);
        if (delta > WATCHDOG_TIMEOUT_MS) {
          console.warn(`[${name_market}] watchdog: no messages for`, delta, 'ms — forcing reconnect');
          // abandon and reconnect immediately
          forceReconnectImmediate('watchdog');
        }
      } catch (e) {
        console.error(`[${name_market}] watchdog tick error`, e);
      }
    }, IDLE_CHECK_MS);
  }

  function clearPing() {
    if (pingInterval) { clearInterval(pingInterval); pingInterval = null; }
  }

  function clearReconnect() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  }

  function scheduleReconnect(delay = BASE_BACKOFF_MS) {
    if (manualClose) return;
    if (reconnectTimer) return; // already scheduled
    if (connecting) return;
    if (socket && (socket.readyState === WebSocket.CONNECTING || socket.readyState === WebSocket.OPEN)) return;

    if (MAX_RECONNECT_ATTEMPTS !== null && reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.warn(`[${name_market}] max reconnect attempts reached`, reconnectAttempts);
      return;
    }

    // capture the connId that scheduled this reconnect — if activeConnId changes later we ignore the callback
    const scheduledFor = activeConnId;
    const backoff = Math.min(MAX_BACKOFF_MS, Math.pow(2, reconnectAttempts) * delay);
    const jitter = Math.floor(Math.random() * 500);
    const finalDelay = Math.max(200, backoff + jitter);

    reconnectAttempts += 1;
    reconnectTimer = setTimeout(() => {
      // if another connection was created since scheduling, don't run
      if (scheduledFor !== activeConnId) {
        reconnectTimer = null;
        return;
      }
      reconnectTimer = null;
      connect();
    }, finalDelay);
  }

  function sendSafe(objOrStr) {
    try {
      if (!socket || socket.readyState !== WebSocket.OPEN) return false;
      if (typeof objOrStr === 'string') socket.send(objOrStr);
      else socket.send(JSON.stringify(objOrStr));
      return true;
    } catch (e) {
      console.warn(`[${name_market}] send failed`, e);
      return false;
    }
  }

  function normalizeBookArray(arr) {
    if (!Array.isArray(arr)) return [];
    return arr.map(item => {
      if (Array.isArray(item)) return [parseFloat(item[0]), parseFloat(item[1])];
      if (item && typeof item === 'object') {
        if (item.p !== undefined && item.s !== undefined) return [parseFloat(item.p), parseFloat(item.s)];
        const p = item.price ?? item.p ?? Object.values(item)[0];
        const s = item.size ?? item.s ?? Object.values(item)[1];
        return [parseFloat(p), parseFloat(s)];
      }
      return null;
    }).filter(Boolean);
  }

  // -----------------------
  // Force reconnect immediately and forget previous socket
  // -----------------------
  function forceReconnectImmediate(reason = 'forced') {
    // If manualClose has been set, do nothing
    if (manualClose) return;

    try {
      // cancel pending reconnect timers for previous connection
      clearReconnect();
      // increment connection id so all old handlers become no-ops
      connId += 1;
      activeConnId = connId;

      // attempt graceful unsubscribe/send if possible, but don't wait for it
      try {
      //  const { unsubPayload } = buildSubscribePayload(`${name_market.toLowerCase()}`, symbolFormatted, mode) || {};
        const topic = `orderbook.50.${String(symbolFormatted).toUpperCase()}`;
        const unsubpayload = { op: 'unsubscribe', args: [topic] };

        if (socket && socket.readyState === WebSocket.OPEN && unsubpayload) {
          try { socket.send(JSON.stringify(unsubpayload)); } catch (e) { /* ignore */ }
        }
      } catch (e) { /* ignore */ }

      // remove handlers from previous socket and close quickly
      try {
        if (socket) {
          try {
            socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null;
          } catch (e) {}
          try { socket.close(); } catch (e) {}
        }
      } catch (e) {}

      // clear timers related to previous socket
      clearPing();
      clearWatchdog();

      // null out references so checks see there's no active socket
      socket = null;
      isSubscribed = false;

      // reset connecting flag to allow immediate reconnect
      connecting = false;

      // schedule immediate connect (no backoff) — but keep minimal spacing to avoid tight loop
      setTimeout(() => {
        try { connect(); } catch (e) { scheduleReconnect(BASE_BACKOFF_MS); }
      }, 50);
    } catch (e) {
      console.error(`[${name_market}] forceReconnectImmediate error`, e);
      scheduleReconnect(BASE_BACKOFF_MS);
    }
  }

  // -----------------------
  // Core connect logic
  // -----------------------
  function connect() {
    try {
      if (connecting) return;
      const now = Date.now();
      if (now - lastConnectAttempt < 400) {
        // too-quick calls -> schedule with small delay
        scheduleReconnect(500);
        return;
      }
      lastConnectAttempt = now;

      manualClose = false;
      connecting = true;

      // create a new connection id for this socket
      connId += 1;
      const thisConnId = connId;
      activeConnId = thisConnId;

      // close previous socket quickly (we already abandoned it on forceReconnectImmediate normally)
      if (socket) {
        try { socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null; } catch (e) {}
        try { socket.close(); } catch (e) {}
        socket = null;
      }

      const ws = new WebSocket(endpoint);
      socket = ws; // assign to shared reference

      // connect timeout — if still connecting after CONNECT_TIMEOUT_MS, abandon and reconnect
      const connectTimeout = setTimeout(() => {
        if (thisConnId !== activeConnId) return; // stale
        if (ws && ws.readyState === WebSocket.CONNECTING) {
          console.warn(`[${name_market}] connect timed out — closing socket`);
          try { ws.close(); } catch (e) {}
        }
      }, CONNECT_TIMEOUT_MS);

      ws.onopen = () => {
        // ignore stale sockets
        if (thisConnId !== activeConnId) return;

        console.info(`[${name_market}] connected`, endpoint, 'connId', thisConnId);
        clearTimeout(connectTimeout);
        reconnectAttempts = 0;
        connecting = false;

        lastMessageAt = Date.now();
        // removed startIdleTimer(); — watchdog will handle idle detection
        startWatchdog(thisConnId);
        
        // send subscribe payload (1:1 from your buildSubscribePayload)
        try {
         // const { subscribePayload } = buildSubscribePayload(`${name_market.toLowerCase()}`, symbolFormatted, mode);
            const topic = `orderbook.50.${String(symbolFormatted).toUpperCase()}`;
            const payload = { op: 'subscribe', args: [topic] };
          if (payload) {
            try { ws.send(JSON.stringify(payload)); isSubscribed = true; } catch (e) { /* ignore */ }
          }
        } catch (e) { console.warn(`[${name_market}] buildSubscribePayload error`, e); }

        try {
          sendPingNow();
        } catch (e) {}
        // optional app-level ping
        clearPing();
        if (typeof sendPingNow === 'function') {
          pingInterval = setInterval(() => {
            if (thisConnId !== activeConnId) return; // safety
            try { sendPingNow(); } catch (e) { /* ignore */ }
          }, PING_INTERVAL_MS);
        }
      };

      ws.onmessage = (ev) => {
        // ignore stale events
        if (thisConnId !== activeConnId) return;
        try {
          lastMessageAt = Date.now();

          if (typeof ev.data === 'string') {
            processMessage(ev.data);
            return;
          }

          if (ev.data instanceof ArrayBuffer) {
            const text = new TextDecoder().decode(new Uint8Array(ev.data));
            processMessage(text);
            return;
          }

          if (ev.data instanceof Blob) {
          const reader = new FileReader();
          reader.onload = () => {
            try { processMessage(reader.result); } catch (e) { console.error(`[${name_market}] blob parse error`, e); }
          };
          reader.readAsText(ev.data);
          return;
          }

        } catch (e) {
          console.error(`[${name_market}] onmessage error`, e);
        }
      };

      ws.onclose = (ev) => {
        // ignore stale closes
        if (thisConnId !== activeConnId) return;
        console.info(`[${name_market}] closed`, ev && ev.code);
        isSubscribed = false;
        clearPing();
        clearWatchdog();
        connecting = false;
        if (!manualClose) scheduleReconnect(BASE_BACKOFF_MS);
      };

      ws.onerror = (e) => {
        if (thisConnId !== activeConnId) return;
        console.error(`[${name_market}] ws error`, e);
      };

    } catch (e) {
      console.error(`[${name_market}] connect exception`, e);
      connecting = false;
      scheduleReconnect(BASE_BACKOFF_MS);
    }
  }

  // -----------------------
  // Message processing (unchanged)
  // -----------------------
  function processMessage(text) {
    if (!text) return;
    let msg;
    try {
      msg = JSON.parse(text);
    } catch (e) {
      // ignore non-json
      return;
    }

    // Ignore ping/pong/control messages that don't carry orderbook
    if (msg.op === 'pong' || msg.op === 'ping') return;
    if (msg.type && (msg.type === 'pong' || msg.type === 'ping')) return;

    // Subscription responses might be like {ret_msg: 'success', op: 'subscribe', topic: 'orderbook.50.BTCUSDT' }
    // We'll ignore non-orderbook topics
    const topic = msg.topic || (msg.arg && msg.arg.topic) || null;
    if (!topic || !String(topic).toLowerCase().includes('orderbook')) {
      return;
    }

    // Expected shapes: { topic, type: 'snapshot'|'delta', ts, data: { s, b, a, u, seq }, cts }
    const t = msg.type || (msg.data && msg.data.type) || null;
    const data = msg.data || msg; // sometimes nested differently

    try {
      // snapshot message or forced snapshot via u===1
      if (msg.type === 'snapshot' || (data && data.u === 1) ) {
        applySnapshot(data);
        const { asks, bids } = mapToSortedArrays();
        if ((asks.length || bids.length) && onData) {
          try {
            onData({
              market: `${name_market}`,
              symbol: symbolOut,
              asks,
              bids,
              raw: msg,
              topic,
              timestamp: Date.now()
            });
          } catch (e) { console.error(`[${name_market}] onData callback error`, e); }
        }
        return;
      }

      // delta update
      if (msg.type === 'delta' || t === 'delta') {
        // If no snapshot yet, ignore delta (will wait for snapshot)
        if (!hasSnapshot) return;

        applyDelta(data);
        const { asks, bids } = mapToSortedArrays();
        // Only forward if there is non-empty update
        if ((asks.length || bids.length) && onData) {
          try {
            onData({
              market: `${name_market}`,
              symbol: symbolOut,
              asks,
              bids,
              raw: msg,
              topic,
              timestamp: Date.now()
            });
          } catch (e) { console.error(`[${name_market}] onData callback error`, e); }
        }
        return;
      }

      // Some servers send snapshot as data.type or different nesting — attempt a best-effort detection:
      if (data && (data.b || data.a)) {
        // If data includes bids/asks but no explicit type, treat as snapshot if we don't yet have one
        if (!hasSnapshot) {
          applySnapshot(data);
        } else {
          // otherwise treat as delta-ish update
          applyDelta(data);
        }
        const { asks, bids } = mapToSortedArrays();
        if ((asks.length || bids.length) && onData) {
          try {
            onData({
              market: `${name_market}`,
              symbol: symbolOut,
              asks,
              bids,
              raw: msg,
              topic,
              timestamp: Date.now()
            });
          } catch (e) { console.error(`[${name_market}] onData callback error`, e); }
        }
        return;
      }

    } catch (e) {
      console.error(`[${name_market}] processMessage error`, e);
    }
  }

  // -----------------------
  // Public API
  // -----------------------
  function subscribe(cb) {
    onData = cb;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      connect();
    } else {
      if (!isSubscribed) {
        try {
        //  const { subscribePayload } = buildSubscribePayload(`${name_market.toLowerCase()}`, symbolFormatted, mode);
            const topic = `orderbook.50.${String(symbolFormatted).toUpperCase()}`;
            const payload = { op: 'subscribe', args: [topic] };

          if (payload) { sendSafe(payload); isSubscribed = true; }
        } catch (e) { console.warn(`[${name_market}] subscribe error`, e); }
      }
    }

    return () => {
      try {
       // const { unsubPayload } = buildSubscribePayload(`${name_market.toLowerCase()}`, symbolFormatted, mode);
        const topic = `orderbook.50.${String(symbolFormatted).toUpperCase()}`;
        const unsubpayload = { op: 'unsubscribe', args: [topic] };

        if (unsubpayload && socket && socket.readyState === WebSocket.OPEN) {
          try { sendSafe(unsubpayload); } catch (e) { /* ignore */ }
        }
      } catch (e) { console.warn(`[${name_market}] unsubscribe error`, e); }

      // fully close and disable reconnects
      manualClose = true;
      // increment conn id so any in-flight handlers are ignored
      connId += 1;
      activeConnId = connId;

      try { if (socket) { socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null; socket.close(); } } catch (e) {}
      socket = null;
      isSubscribed = false;
      clearPing();
      clearWatchdog();
      clearReconnect();
    };
  }

  function close() {
    manualClose = true;
    connId += 1; activeConnId = connId;
    try { if (socket) { socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null; socket.close(); } } catch (e) {}
    socket = null;
    isSubscribed = false;
    clearPing();
    clearWatchdog();
    clearReconnect();
  }

  function connectAndSubscribe() { connect(); }

  return { connect: connectAndSubscribe, subscribe, close };
}

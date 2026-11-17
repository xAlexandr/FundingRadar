import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { fetchData, fetchCoinList } from '../api/api.js';
import SpreadChart from './SpreadChart.js';
import SpreadChart2 from './SpreadChart2.js';
import '../Main.css';
import useAuth from './useAuth';
import AlertBell from './Alert.js';
import { createConnector} from '../ws/connectors';
import { formatSymbolForExchange } from '../ws/connectors/utils';
import localMultipliers from '../ws/multipliers/multipliers.json';

function openNewTab(){
  window.Telegram.WebApp.openTelegramLink('https://t.me/funding_cryptoprojects_bot/FundingBot?startapp=_newtab_'+String(parseInt(Math.random()*10000000000)))
}


const Home = () => {
  const { t } = useTranslation();
  // Состояния для данных
  // const [coin, setCoin] = useState('BTC');
  // const [market1, setMarket1] = useState('Bybit');
  // const [market2, setMarket2] = useState('Mexc');
  // const [spOrFt, setSpOrFt] = useState('futures');
   const savedTradePath = JSON.parse(localStorage.getItem("lastTrade")) || {
    spOrFt: "futures",
    market1: "Bybit",
    market2: "Mexc",
    coin: "BTC",
};

    // ===== helpers for dex display/server conversion =====
const DEX_NETWORK_LEN = 3;

function displayFromRawSymbol(raw) {
  // raw может быть "BSC_ETH" или "BTCUSDT" и т.д.
  if (!raw) return "";
  const s = String(raw).toUpperCase();
  if (s.includes('_')) {
    return s.replace('_', ''); // BSC_ETH -> BSCETH
  }
  // если уже без подчёркивания — оставляем
  return s;
}

function serverSymbolFromDisplay(display, market) {
  // display: что пользователь видит/вводит (например BSCETH или BTCUSDT)
  // если market === 'Dex' — вернём BSC_ETH (вставим _ после 3 символов)
  if (!display) return "";
  let s = String(display).toUpperCase();
  if (String(market || '').toLowerCase() === 'dex') {
    // если уже содержит '_' — нормализуем (на всякий)
    if (s.includes('_')) return s;
    if (s.length > DEX_NETWORK_LEN) {
      return s.slice(0, DEX_NETWORK_LEN) + '_' + s.slice(DEX_NETWORK_LEN);
    } else {
      // не хватает длины — вернём как есть (сервер разберёт)
      return s;
    }
  }
  // для обычных рынков: обычно полная форма (например BTCUSDT) — просто вернуть uppercase
  return s;
}

  const [entryPrice1, setEntryPrice1] = useState(JSON.parse(localStorage.getItem("entryPrice1")) ?? "");
const [entryPrice2, setEntryPrice2] = useState(JSON.parse(localStorage.getItem("entryPrice2")) ?? "");
const [exitPrice1, setExitPrice1] = useState(JSON.parse(localStorage.getItem("exitPrice1")) ?? "");
const [exitPrice2, setExitPrice2] = useState(JSON.parse(localStorage.getItem("exitPrice2")) ?? "");
const [useEntrySpread, setUseEntrySpread] = useState(false);
const [useExitSpread, setUseExitSpread] = useState(false);
const [showFuncDiv, setShowFuncDiv] = useState(JSON.parse(localStorage.getItem("showFuncDiv")) ?? false);

const [useZoomGraph2, setUseZoomGraph2] = useState(JSON.parse(localStorage.getItem("useZoomGraph2")) ?? false);


// Второе поле монеты
const [showCoin2, setShowCoin2] = useState(false);


// multipliers / kucoin token от сервера по запросу info
const multiplier1Ref = useRef(null);
const multiplier2Ref = useRef(null);

const [kucoinTokenState, setKucoinTokenState] = useState(null);


useEffect(() => {
  localStorage.setItem("showFuncDiv", JSON.stringify(showFuncDiv));
}, [showFuncDiv]);

useEffect(() => {
  localStorage.setItem("useZoomGraph2", JSON.stringify(useZoomGraph2));
}, [useZoomGraph2]);

useEffect(() => {
  localStorage.setItem("entryPrice1", JSON.stringify(entryPrice1));
  localStorage.setItem("entryPrice2", JSON.stringify(entryPrice2));
  localStorage.setItem("exitPrice1", JSON.stringify(exitPrice1));
  localStorage.setItem("exitPrice2", JSON.stringify(exitPrice2));
}, [entryPrice1, entryPrice2, exitPrice1, exitPrice2]);


const socketRef = useRef(null);
const intervalRef = useRef(null);
//const reconnectTimeoutRef = useRef(null);
// ---------- ADD START: connectors + debouncedCoin2 + internal refs ----------
const connectorsRef = useRef({ c1: null, c2: null});
const lastProcessedRef = useRef({ c1: 0, c2: 0, gateioC1: 0, gateioC2: 0});
const latestOrderbooksRef = useRef({ c1: null, c2: null});
// track last symbol actually used by connectors (to avoid unnecessary reconnects)
const lastSymbolRef = useRef({ c1: null, c2: null });
const dexSubscriptionsRef = useRef(new Set());






// Функция для обработки ввода (разрешаем только цифры и точку)
const handleInputChange = (event, type) => {
  let value = event.target.value;

  // Заменяем запятую на точку и убираем пробелы
  value = value.replace(/,/g, ".").replace(/\s/g, "");

  // Регулярное выражение для проверки: только цифры и одна точка
  if (/^\d*\.?\d*$/.test(value) || value === "") {
    if (type === "entryPrice1") {
      setEntryPrice1(value);
    } else if (type === "entryPrice2") {
      setEntryPrice2(value);
    } else if (type === "exitPrice1") {
      setExitPrice1(value);
    } else if (type === "exitPrice2") {
      setExitPrice2(value);
    }
  }
};

const toggleEntrySpread = () => setUseEntrySpread(!useEntrySpread);
const toggleExitSpread = () => setUseExitSpread(!useExitSpread);



  const navigate = useNavigate();
  const { spOrFtP, market1P, market2P, coinP } = useParams(); // Получаем параметры из URL
  //console.log("Params from URL:", spOrFtP, market1P, market2P, coinP); // Отладка
  // Устанавливаем параметры при первом рендере
  // const [market1, setMarket1] = useState(market1P || "Bybit");
  // const [market2, setMarket2] = useState(market2P || "Mexc");
  // const [spOrFt, setSpOrFt] = useState(spOrFtP || "futures");
  // const [coin, setCoin] = useState(coinP || "BTC");
  // Инициализируем параметры из URL или localStorage
  // Загружаем сохраненный путь из localStorage
 
const { isAuthenticated } = useAuth(); // Получаем состояние аутентификации
// Разрешаем компоненту рендериться и показывать спиннер пока не придёт подтверждение подписки
const [authChecked, setAuthChecked] = useState(true);

const [hasSubscribe, setHasSubscribe] = useState(null);

// когда придёт явная инфа о подписке — можно логировать/реагировать, но authChecked оставляем true
useEffect(() => {
  if (hasSubscribe !== null) {
    console.debug("hasSubscribe changed ->", hasSubscribe);
  }
}, [hasSubscribe]);


//console.log('SUB', hasSubscribe)

// Используем `useState`, но изначально не полагаемся только на `useParams`
const [spOrFt, setSpOrFt] = useState(spOrFtP || savedTradePath.spOrFt);
const [market1, setMarket1] = useState(market1P || savedTradePath.market1);
const [market2, setMarket2] = useState(market2P || savedTradePath.market2);

// coin — full display (например "BSCETH")
// coinPrefix — первые 3 символа для Dex (редактируемые и видимые в квадратике)
// coinInputSuffix — то, что идёт после префикса (в инпуте)
const [coin, setCoin] = useState(coinP ? displayFromRawSymbol(coinP) : (savedTradePath.coin ? displayFromRawSymbol(savedTradePath.coin) : "BTC"));
const [coinPrefix, setCoinPrefix] = useState(() => {
  const init = coin || "";
  return init.slice(0, DEX_NETWORK_LEN);
});
const [coinInputSuffix, setCoinInputSuffix] = useState(() => {
  const init = coin || "";
  return init.length > DEX_NETWORK_LEN ? init.slice(DEX_NETWORK_LEN) : "";
});

const [coin2, setCoin2] = useState(coin || JSON.parse(localStorage.getItem("coin2")) || "ETH");
useEffect(() => {
  localStorage.setItem("coin2", JSON.stringify(coin2));
}, [coin2]);
const [debouncedCoin2, setDebouncedCoin2] = useState(coin);
const [debouncedCoin, setDebouncedCoin] = useState(coin); // Добавляем отложенное состояние

const [entrySpread, setEntrySpread] = useState('wait');  // Спред входа
  const [exitSpread, setExitSpread] = useState('wait');   // Спред выхода
  const [effective_in, setEffective_in] = useState(null);  // Спред входа
  const [effective_out, setEffective_out] = useState(null);   // Спред выхода
  const [time, setTime] = useState("");  // Время для отображения

  const [histEntrySpread, setHistEntrySpread] = useState('wait');  // Спред входа
  const [histExitSpread, setHistExitSpread] = useState('wait');   // Спред выхода
  const [histTime, setHistTime] = useState("");  // Время для отображения

  const [depthGlass, setDepthGlass] = useState(JSON.parse(localStorage.getItem("depth")) ?? "3")

  const changeDepth = () => {
    if (depthGlass == "3")
    {
      setDepthGlass(5);
    } else {
      setDepthGlass(3);
    }
  };

  useEffect(() => {
    localStorage.setItem("depth", JSON.stringify(depthGlass));
  }, [depthGlass]);
  

  const [depthValue, setDepthValue] = useState(JSON.parse(localStorage.getItem("depthValue")) ?? "0");


  const debouncedDepth = useRef(depthValue);
 // const [debouncedDepth, setDebouncedDepth] = useState(depthValue);

  useEffect(() => {
    localStorage.setItem("depthValue", JSON.stringify(debouncedDepth.current));
  }, [debouncedDepth.current]);

  const [useDepth, setUseDepth] = useState(JSON.parse(localStorage.getItem("useDepth")) ?? false);

  useEffect(() => {
    localStorage.setItem("useDepth", JSON.stringify(useDepth));
  }, [useDepth]);


  

const changeUseDepth = () => {
  if (!useDepth) {
    // включаем — используем немедленно текущее значение depthValue (не ждём debounce)
    const dv = parseFloat(depthValue || 0) || 0;
    setUseDepth(true);
    // обновим debouncedDepth синхронно, чтобы последующие эффекты увидели значение
    debouncedDepth.current = String(dv);
    // сразу пересчитаем с текущим depth (без ожидания)
    if (market1 == 'Dex')
    {
      computeEffectiveWithDepth(dv);
    }
    
  } else {
    // выключаем
    setUseDepth(false);
    // очистим effective
    setEffective_in(null);
    setEffective_out(null);
    // восстановим top-of-book значения
    const ob1 = latestOrderbooksRef.current.c1;
    const ob2 = latestOrderbooksRef.current.c2;
    if (ob1 && ob2) {
      const top_in = (ob2.bids.length && ob1.asks.length) ? (((ob2.bids[0][0] / ob1.asks[0][0]) - 1) * 100) : 'wait';
      const top_out = (ob2.asks.length && ob1.bids.length) ? (((ob2.asks[0][0] / ob1.bids[0][0]) - 1) * 100) : 'wait';
      setEntrySpread(top_in === 'wait' ? 'wait' : Number(top_in.toFixed(2)));
      setExitSpread(top_out === 'wait' ? 'wait' : Number(top_out.toFixed(2)));
    }
  }
};

  // Если coin меняется синхронизируем coin2
useEffect(() => {
  if (!showCoin2)
  {
    setCoin2(coin);
  } 
}, [coin, showCoin2])


useEffect(() => {
  const handler = setTimeout(() => {
    // debouncedCoin2 — серверный формат, но при отсутствии showCoin2 используем debouncedCoin
    if (!showCoin2) {
      setDebouncedCoin2(serverSymbolFromDisplay(coin, market2));
    } else {
      setDebouncedCoin2(serverSymbolFromDisplay(coin2, market2));
    }
  }, 2000);
  return () => clearTimeout(handler);
}, [coin2, showCoin2, market2, coin, market1]);



// --- ADD: remember separate coins for DEX and for regular exchanges ---
const [savedDexCoin, setSavedDexCoin] = useState(() => {
  return localStorage.getItem('savedDexCoin') || 'BSCETH';
});
const [savedCexCoin, setSavedCexCoin] = useState(() => {
  return localStorage.getItem('savedCexCoin') || 'ETH';
});

// ref to detect that we loaded from URL on initial mount
const urlLoadedRef = useRef(false);


useEffect(() => {
  localStorage.setItem('savedDexCoin', savedDexCoin);
}, [savedDexCoin]);

useEffect(() => {
  localStorage.setItem('savedCexCoin', savedCexCoin);
}, [savedCexCoin]);






  useEffect(() => {
    const closeWebSocket = () => {
      return new Promise((resolve, reject) => {
          if (socketRef.current) {
           //   console.log("Закрываем WebSocket");

              socketRef.current.onclose = () => {
                //  console.log("WebSocket успешно закрыт");
                  resolve(); // Когда сокет закроется, вызываем resolve
              };

              socketRef.current.close();
              clearInterval(intervalRef.current);
              intervalRef.current = null;
              socketRef.current = null;
          } else {
              resolve(); // Если нет сокета, сразу разрешаем промис
          }
      });
  };


  // Очистка графика SpreadChart2
  setHistEntrySpread("wait");
  setHistExitSpread("wait");
  setHistTime("");

    const connectWebSocket = () => {
        if (socketRef.current) {
          //  console.log("Закрываем предыдущее соединение перед созданием нового");
            socketRef.current.close();
            clearInterval(intervalRef.current);
        //    clearTimeout(reconnectTimeoutRef.current);
            socketRef.current = null;
        }

        const token = localStorage.getItem("accessToken");
        if (!token) {
            console.warn("Нет токена для WebSocket подключения");
            return;
        }

        const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        
        const isDebug = process.env.REACT_APP_DEBUG === 'true';

          // Локальный или прод-адрес
          const target = isDebug
            ? "localhost:8000"
            : window.location.host;

        const socket = new WebSocket(`${protocol}://${target}/ws/monitor/?token=${token}`);
      //  const socket = new WebSocket(`wss://cp-bot.ru:8000/ws/monitor/?token=${token}`);
        socketRef.current = socket;
        
        const sendInfo = () => {
          try {
            if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
              // Если showCoin2=false — уверенно отправляем coin2 = debouncedCoin (fallback),
              // чтобы сервер всегда мог вернуть multipliers для обеих сторон.
              const coin2ToSend = showCoin2 ? (debouncedCoin2 || debouncedCoin) : debouncedCoin;
              socketRef.current.send(JSON.stringify({
                action: "info",
                info_type: "multipliers",
                market1,
                market2,
                coin1: debouncedCoin,
                coin2: coin2ToSend
              }));
            }
          } catch (e) { console.error("sendInfo error", e); }
        };

        socket.onopen = () => {
       //     console.log("WebSocket подключен");

            const sendMessage = () => {
                if (socket.readyState === WebSocket.OPEN) {
                  const coin2ToSend = showCoin2 ? (debouncedCoin2 || debouncedCoin) : debouncedCoin;
                    socket.send(
                        JSON.stringify({ 
                          action: "get_history",
                          market1,
                          market2, 
                          coin: debouncedCoin, 
                          coin2: coin2ToSend,
                          sp_or_ft: spOrFt })
                    );
                }
            };

            sendMessage(); // Отправляем сразу после подключения
            sendInfo();
            
            // re-send all desired DEX subscriptions after socket (re)connect
            try {
              if (dexSubscriptionsRef.current && dexSubscriptionsRef.current.size > 0) {
                dexSubscriptionsRef.current.forEach(sym => {
                  try {
                    socket.send(JSON.stringify({ action: "dex_subscribe", symbol: sym }));
                    console.info('[DEX] re-sent subscribe on socket.onopen for', sym);
                    // also clear any retry interval we had stored on connectorsRef for that sym
                    Object.keys(connectorsRef.current).forEach(k => {
                      const rec = connectorsRef.current[k];
                      if (rec && rec.meta && String(rec.meta.formattedSymbol).toUpperCase() === String(sym).toUpperCase()) {
                        if (rec._dexRetryId) { clearInterval(rec._dexRetryId); rec._dexRetryId = null; }
                        // set tries to max so local retry doesn't run any more
                        rec._dexTries = Number.MAX_SAFE_INTEGER;
                      }
                    });
                  } catch(err) {
                    console.warn('[DEX] re-subscribe failed for', sym, err);
                  }
                });
              }
            } catch(e) { console.warn('onopen dex resubscribe failed', e); }


            intervalRef.current = setInterval(sendMessage, 3000); // Повторяем запросы

        };

        socket.onmessage = (event) => {
          try {
            const result = JSON.parse(event.data);
            if (result.error) {
              setHasSubscribe(false);
              return;
            }
            // multipliers / token info
            if (result.type === "info_multipliers") {
              setHasSubscribe(true);
              multiplier1Ref.current = result.multiplier1 ?? null;
              multiplier2Ref.current = result.multiplier2 ?? null;
              if (result.kucoin_token) setKucoinTokenState(result.kucoin_token);
            //  console.log('INFO MULTIPLIERS', result);
              return;
            }
            if (result.type === "info_kucoin_token") {
              setKucoinTokenState(result.kucoin_token ?? null);
              return;
            }

            // server-side DEX update (we subscribed via dex_subscribe)
            // server-side DEX update (we subscribed via dex_subscribe)
            // accept both "dex_update" and "dex.update" just in case server sends either form
            if (result.type === "dex.update" || result.type === "dex_update") {
              // result.data is object or null
              const payload = {
                market: 'DEX',
                symbol: result.symbol,
                asks: result.data ? [[result.data.price_usd || result.data.dex_bid || 0, 0]] : [],
                bids: result.data ? [[result.data.price_usd || result.data.dex_bid || 0, 0]] : [],
                timestamp: result.timestamp || Date.now()
              };
              // route to appropriate side
              if ((market1 || '').toLowerCase() === 'dex' && (debouncedCoin === result.symbol || (showCoin2 && debouncedCoin2 === result.symbol))) {
                const targetIdx = (debouncedCoin === result.symbol) ? 1 : ((debouncedCoin2 === result.symbol) ? 2 : 1);
                onOrderbookReceived(payload, targetIdx);
              } else if ((market2 || '').toLowerCase() === 'dex' && (debouncedCoin2 === result.symbol || debouncedCoin === result.symbol)) {
                const targetIdx = (debouncedCoin2 === result.symbol) ? 2 : ((debouncedCoin === result.symbol) ? 1 : 2);
                onOrderbookReceived(payload, targetIdx);
              }
              return;
            }


            // server can also send proxied orderbook from remote exchanges: expect payload similar to {market, symbol, asks, bids, ...}
            if (result.market && (result.asks || result.bids)) {
              // Determine which side: match by market and symbol to either 1 or 2
              const rmarket = (result.market || '').toLowerCase();
              // choose index by comparing to market1/market2 or symbol equality
              if (rmarket === (market1 || '').toLowerCase()) {
                onOrderbookReceived(result, 1);
              } else if (rmarket === (market2 || '').toLowerCase()) {
                onOrderbookReceived(result, 2);
              } else {
                // If symbol matches coin/coin2 — route by that
                if (result.symbol && (result.symbol.toUpperCase().startsWith(debouncedCoin.toUpperCase()))) {
                  onOrderbookReceived(result, 1);
                } else if (result.symbol && (showCoin2 && result.symbol.toUpperCase().startsWith(debouncedCoin2.toUpperCase()))) {
                  onOrderbookReceived(result, 2);
                }
              }
              return;
            }

            // existing periodic / constant / periodic types from server
            if (result.type === "constant") {
              // server constant is same format as your front-end dataObj; just pass it through
              // Update UI and spread values (server already computed effective values but we re-calc on client for consistent behavior)
              setData(result);
              setHasSubscribe(true);
              setEntrySpread(result.in);
              setExitSpread(result.out);
              setEffective_in(result.effective_in);
              setEffective_out(result.effective_out);
              setTime(new Date().toLocaleTimeString());
              return;
            }

            // periodic (history)
            if (result.type === "periodic") {
              setHistEntrySpread(result.spreads_in === "wait" || result.spreads_in === "Error" ? 0 : result.spreads_in);
              setHistExitSpread(result.spreads_out === "wait" || result.spreads_out === "Error" ? 0 : result.spreads_out);
              const moscowTimes = (result.spreads_time || []).map(t => {
                const dt = new Date(t);
                return dt.getHours().toString().padStart(2,"0") + ":" + dt.getMinutes().toString().padStart(2,"0");
              });
              setHistTime(moscowTimes);
              return;
            }

            // fallback: log unknown message
            console.debug("Unhandled WS message", result);
          } catch (e) {
            console.error("socket.onmessage error", e);
          }
        };


        socket.onerror = (error) => {
            console.error("WebSocket ошибка:", error);
        };

        socket.onclose = () => {
        //    console.log("WebSocket отключен, пробую переподключиться...");

            // socket closed — clear running retry intervals (we will re-subscribe on next onopen)
            try {
              Object.keys(connectorsRef.current).forEach(k => {
                const rec = connectorsRef.current[k];
                if (rec && rec._dexRetryId) {
                  clearInterval(rec._dexRetryId);
                  rec._dexRetryId = null;
                }
                // mark not-subscribed
                if (rec) rec._dexSubscribed = false;
              });
            } catch(e) { /* ignore */ }

            socketRef.current = null;
            clearInterval(intervalRef.current);
            intervalRef.current = null;

            // reconnectTimeoutRef.current = setTimeout(connectWebSocket, 3000);
        };
    };

    connectWebSocket();

    return () => {
    //  console.log("Закрываем WebSocket при размонтировании");
      closeWebSocket(); // Ждем, пока WebSocket закроется перед размонтированием
      clearInterval(intervalRef.current);
    };
}, [market1, market2, debouncedCoin, spOrFt, debouncedCoin2]);


// Обработать параметры из URL ТОЛЬКО ОДИН РАЗ при первом маунте.
// Если компонент пермонтируется заново — эффект выполнится снова, что нормально.
useEffect(() => {
  // защита: если уже обработано — не делаем снова
  if (urlLoadedRef.current) return;

  if (spOrFtP && market1P && market2P && coinP) {
    // пришли параметры из URL — используем их (override saved)
    urlLoadedRef.current = true;

    setSpOrFt(spOrFtP);
    setMarket1(market1P);
    setMarket2(market2P);

    const display = displayFromRawSymbol(coinP); // BSCETH или ETH etc.
    setCoin(display);

    if (String(market1P).toLowerCase() === 'dex') {
      const prefix = display.slice(0, DEX_NETWORK_LEN);
      const suffix = display.length > DEX_NETWORK_LEN ? display.slice(DEX_NETWORK_LEN) : '';
      setCoinPrefix(prefix);
      setCoinInputSuffix(suffix);
      // coin2 в случае перехода по ссылке — это суффикс (без сети)
      setCoin2(suffix || 'ETH');
      setSavedDexCoin(display);
    } else {
      // для обычных рынков — coin2 оставляем как сохранено или same as coin
      setSavedCexCoin(display);
      setCoin2(display || (savedCexCoin));
    }
  } else {
    // параметры отсутствуют — устанавливаем их из lastTrade в localStorage
    urlLoadedRef.current = true;

    setSpOrFt(savedTradePath.spOrFt);
    setMarket1(savedTradePath.market1);
    setMarket2(savedTradePath.market2);
    const display = displayFromRawSymbol(savedTradePath.coin);
    setCoin(display);
    // set suffix/prefix accordingly if initial market is dex
    if (String(savedTradePath.market1).toLowerCase() === 'dex') {
      setCoinPrefix(display.slice(0, DEX_NETWORK_LEN));
      setCoinInputSuffix(display.length > DEX_NETWORK_LEN ? display.slice(DEX_NETWORK_LEN) : '');
      setCoin2(display.length > DEX_NETWORK_LEN ? display.slice(DEX_NETWORK_LEN) : display);
    } else {
      setCoin2(JSON.parse(localStorage.getItem('coin2')) || display);
    }
  }
  // выполняем этот эффект только при маунте
}, []); // пустой deps => один раз при mount



  // Сохраняем путь в `localStorage`, когда изменяются параметры торговли
  useEffect(() => {
    const tradeData = { spOrFt, market1, market2, coin };
    localStorage.setItem("lastTrade", JSON.stringify(tradeData));
    if (spOrFt && market1 && market2 && coin) {
    navigate(`/trade/${spOrFt}/${market1}/${market2}/${coin}/`, { replace: true });
    }
}, [spOrFt, market1, market2, coin]);

useEffect(() => {
  // если мы только что загрузились из URL — не перезаписывать (clear flag and keep URL value)
  if (urlLoadedRef.current) {
    urlLoadedRef.current = false;
    return;
  }
  if (String(market1 || '').toLowerCase() === 'dex') {
    // при переключении на DEX — используем отдельно сохранённую dex-монету (или дефолт)
    const val = savedDexCoin || 'BSCETH';
    setCoin(val);
    setCoinPrefix(val.slice(0, DEX_NETWORK_LEN));
    setCoinInputSuffix(val.length > DEX_NETWORK_LEN ? val.slice(DEX_NETWORK_LEN) : '');
    // coin2 = суффикс
    const suffix = val.length > DEX_NETWORK_LEN ? val.slice(DEX_NETWORK_LEN) : val;
    setCoin2(suffix || 'ETH');
  } else {
    // на любую другую биржу — используем сохранённую обычную монету
    const val = savedCexCoin || 'ETH';
    setCoin(val);
    // для non-dex префиксы/суффиксы не важны — сбрасываем
    setCoinPrefix(val.slice(0, DEX_NETWORK_LEN));
    setCoinInputSuffix(val.length > DEX_NETWORK_LEN ? val.slice(DEX_NETWORK_LEN) : '');
    setCoin2(val);
  }
}, [market1]); // можно добавить savedDexCoin/savedCexCoin при желании


// Посылаем info при изменении рынков/монет (если соединение открыто
useEffect(() => {
  const sendInfoIfOpen = () => {
    try {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify({
          action: "info",
          info_type: "multipliers",
          market1,
          market2,
          coin1: debouncedCoin,
          coin2: showCoin2 ? debouncedCoin2 : null
        }));
      }
    } catch (e) { console.error("sendInfoIfOpen error", e); }
  };
  // вызываем сразу
  sendInfoIfOpen();
}, [market1, market2, debouncedCoin, debouncedCoin2, showCoin2])



  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [dataLoaded, setDataLoaded] = useState(false); // Состояние для отслеживания первого обновления данных
  const [previousData, setPreviousData] = useState(null); // Для отслеживания изменения данных


  const [coinList, setCoinList] = useState([]); // Список всех монет
  const [filteredCoins, setFilteredCoins] = useState([]); // Фильтрованный список
  const [showDropdown, setShowDropdown] = useState(false); // Показывать ли список

  const [isInitialRender, setIsInitialRender] = useState(true); // Состояние для первого рендера





  // Загружаем список монет при первом рендере
  useEffect(() => {
    
    const loadCoins = async () => {
      try {
        const coins = await fetchCoinList(); // Загружаем список монет
        setCoinList(coins);
      } catch (error) {
        console.error("Ошибка загрузки списка монет:", error);
      }
    };
    setTimeout(()=>{
      loadCoins();
    }, 3000)
  }, []);

  // ⏳ Дебаунс: обновляем `debouncedCoin` через 2 секунды после последнего ввода
  useEffect(() => {
  const handler = setTimeout(() => {
    // debouncedCoin — всегда в формате, который требуется серверу
    setDebouncedCoin(serverSymbolFromDisplay(coin, market1));
  }, 2000);

  return () => clearTimeout(handler);
}, [coin, market1]); // если меняется market1 — надо пересчитать формат


  // ⏳ Дебаунс: обновляем `debouncedCoin` через 2 секунды после последнего ввода
  useEffect(() => {
    const handlerDepth = setTimeout(() => {
      debouncedDepth.current = depthValue; // Через 2 сек. обновляем отложенное состояние
    }, 200);

    return () => clearTimeout(handlerDepth); // Очищаем таймер при новом вводе
  }, [depthValue]);



  const handleDepthInput = (e) => {
    const value = e.target.value.replace(/\D/g, "").slice(0, 6); // Убираем не цифры и ограничиваем 6 знаков
    setDepthValue(value);
  };
 
  // Фильтрация монет при вводе
  // Фильтрация монет при вводе (с учётом DEX-формата)
  // вызывается onChange у основного input
const handleCoinInput = (e) => {
  // введённое пользователем (в нашем UI — только суффикс, без префикса)
  let typed = String(e.target.value || '').toUpperCase();
  // очищаем нежелательные символы и подчищаем _
  typed = typed.replace(/_/g, '').replace(/\s+/g, '').replace(/[^A-Z0-9]/g, '');

  // Если market1 — DEX: храним prefix отдельно (первые DEX_NETWORK_LEN букв)
  if (String(market1 || '').toLowerCase() === 'dex') {
    // комбинируем текущий префикс + то, что ввёл пользователь
    const combined = (coinPrefix || '') + typed;

    if (combined.length <= DEX_NETWORK_LEN) {
      // всё ушло в префикс; суффикс пустой
      setCoinPrefix(combined);
      setCoinInputSuffix('');
      setCoin(combined); // общий display
      setSavedDexCoin(combined);
    } else {
      const newPrefix = combined.slice(0, DEX_NETWORK_LEN);
      const newSuffix = combined.slice(DEX_NETWORK_LEN);
      setCoinPrefix(newPrefix);
      setCoinInputSuffix(newSuffix);
      setCoin(newPrefix + newSuffix);
      setSavedDexCoin(combined);
    }

    // обновляем suggestions (фильтрацию) по видимой части (суффиксу предпочтительно)
    const filterTerm = ( (coinInputSuffix || '') + typed ).toUpperCase();
    setFilteredCoins(coinList.filter(c => displayFromRawSymbol(c).toUpperCase().includes(filterTerm)));
    setShowDropdown(true);
    setCoin2(typed);
  } else {
    // non-dex: обычное поведение — весь ввод = coin
    const cleaned = typed;
    setCoin(cleaned);
    setCoinPrefix(cleaned.slice(0, DEX_NETWORK_LEN));
    setCoinInputSuffix(cleaned.length > DEX_NETWORK_LEN ? cleaned.slice(DEX_NETWORK_LEN) : '');
    setFilteredCoins(coinList.filter(c => displayFromRawSymbol(c).toUpperCase().includes(cleaned)));
    setShowDropdown(true);
    setSavedCexCoin(cleaned);
  }
};

const handleCoinInputKeyDown = (e) => {
  if (String(market1 || '').toLowerCase() !== 'dex') return;

  // Если нажали Backspace и в поле SUFFIX каретка в начале и суффикс пуст — удаляем из префикса
  if (e.key === 'Backspace') {
    const target = e.target;
    try {
      const selStart = target.selectionStart ?? 0;
      const selEnd = target.selectionEnd ?? 0;
      // если нет выделения и курсор в начале, и суффикс пуст — нужно убрать символ из префикса
      if (selStart === 0 && selEnd === 0 && !(coinInputSuffix && coinInputSuffix.length > 0)) {
        if (coinPrefix && coinPrefix.length > 0) {
          e.preventDefault(); // подавляем стандартный backspace
          const newPrefix = coinPrefix.slice(0, -1);
          setCoinPrefix(newPrefix);
          // recompute coin (prefix + suffix)
          const newCoin = (newPrefix || '') + (coinInputSuffix || '');
          setCoin(newCoin);
          // вручную поставить фокус в input (React обновит value=coinInputSuffix) — курсор в начале
          // после state update курсор будет в конце; если нужно позиционировать — можно установить later via ref
        }
      }
    } catch (err) {
      // безопасно игнорируем
    }
  }
};


const selectCoin = (rawSymbol) => {
  // rawSymbol — тот формат, который ты используешь в списке (например "BSC_ETH" или "BTCUSDT")
  const display = displayFromRawSymbol(rawSymbol); // должно вернуть BSCETH или BTCUSDT w/o USDT (твоя реализация)
  const prefix = display.slice(0, DEX_NETWORK_LEN);
  const suffix = display.length > DEX_NETWORK_LEN ? display.slice(DEX_NETWORK_LEN) : '';
  if (String(market1 || '').toLowerCase() === 'dex') {
    setCoinPrefix(prefix);
    setCoinInputSuffix(suffix);
    setCoin(prefix + suffix);
    setSavedDexCoin(display);
    setCoin2(display.length > DEX_NETWORK_LEN ? display.slice(DEX_NETWORK_LEN) : display);
  } else {
    setCoin(display);
    setCoinPrefix(display.slice(0, DEX_NETWORK_LEN));
    setCoinInputSuffix(display.length > DEX_NETWORK_LEN ? display.slice(DEX_NETWORK_LEN) : '');
    setSavedCexCoin(display);
    if (!showCoin2) setCoin2(display);
  }
  setShowDropdown(false);
};

  // Эффект для обновления данных при изменении параметров
  useEffect(() => {
    if (spOrFt && market1 && market2 && coin) {
      localStorage.setItem("lastTradePath", `/trade/${spOrFtP}/${market1P}/${market2P}/${coinP}/`);
     // console.log('Go Change')
    }
  }, [coin, market1, market2, spOrFt]);

  // Обработчики изменений
  const handleCoinChange = (e) => setCoin(e.target.value);
  const handleMarket1Change = (e) => {
  const newMarket = e.target.value;
  setMarket1(newMarket);

  // Если переключились _на_ Dex — гарантированно включаем второе поле (если оно ещё выключено).
  if (String(newMarket).toLowerCase() === 'dex') {
    if (!showCoin2) {
      setShowCoin2(true); // автоматическое включение для Dex
    }
    return;
  }


  setShowCoin2(false);

};

useEffect(() => {
  if (String(market1).toLowerCase() === 'dex' && !showCoin2) {
    setShowCoin2(true);
  }
// eslint-disable-next-line react-hooks/exhaustive-deps
}, []); // только при первом маунте

  const handleMarket2Change = (e) => setMarket2(e.target.value);
  const handleSpOrFtChange = (e) => setSpOrFt(e.target.value);

  // Функция для обновления стаканов
const renderMarket = (marketData, marketName) => {
  const isAsks = marketName === 'asks1' || marketName === 'asks2';
  let arr = Array.isArray(marketData) ? marketData.slice() : [];

  // guard: ensure arrays contain two-elements [price, amountUsd]
  arr = arr.map(it => {
    if (!Array.isArray(it)) return [0,0];
    return [it[0] ?? 0, it[1] ?? 0];
  });

  // гарантируем порядок: asks ascending, bids descending (source-of-truth)
  if (isAsks) {
    arr.sort((a,b) => (parseFloat(a[0]||0) - parseFloat(b[0]||0)));
  } else {
    arr.sort((a,b) => (parseFloat(b[0]||0) - parseFloat(a[0]||0)));
  }

  const limit = parseInt(depthGlass || 3, 10);
  const limited = arr.slice(0, limit);

  // Если массив короче — дополним нулями
  while (limited.length < limit) limited.push([0,0]);

  // === IMPORTANT: reverse asks for UI orientation ===
  // Раньше asks визуально были "в обратном" порядке — делаем явный reverse,
  // чтобы верхний элемент был ближайшим (или поменяй это поведение если нужно другое).
  const toRender = isAsks ? limited.slice().reverse() : limited;

  return toRender.map((item, index) => {
    const price = item[0] ?? 0;
    const volume = item[1] ?? 0;
    return (
      <div className={`market-container ${isAsks ? 'asks' : 'bids'}`} key={`${marketName}-${index}`}>
        <span className={`price ${checkPriceChange(price)}`}>{price}</span>
        <span className={`volume ${checkVolumeChange(volume)}`}>{formatNumber(Number(volume)) || '0'}$</span>
      </div>
    );
  });
};


// --- REPLACE renderMarket2 (graph variant) ---
// --- REPLACE renderMarket2 (graph variant) ---
const renderMarket2 = (marketData, marketName) => {
  const isAsks = marketName === 'asks1' || marketName === 'asks2';
  let arr = Array.isArray(marketData) ? marketData.slice() : [];

  arr = arr.map(it => {
    if (!Array.isArray(it)) return [0,0];
    return [it[0] ?? 0, it[1] ?? 0];
  });

  const market1IsDex = String(market1 || '').toLowerCase() === 'dex';

  // Если первая биржа — Dex:
  // - не показываем asks1 вообще
  // - показываем для bids1 только top bid (центрально, зелёным)
  if (market1IsDex) {
    if (marketName === 'asks1') {
      // не рендерим asks для Dex в первой стороне
      return null;
    }
    if (marketName === 'bids1') {
      // упорядочим bids (desc) и возьмём top
      arr.sort((a,b) => (parseFloat(b[0]||0) - parseFloat(a[0]||0)));
      const top = arr.length ? (arr[0][0] ?? 0) : 0;
      return (
        <div className={`market-container-graph dex-only bids`} key={`${marketName}-dex`}>
          <span className={`price dex-price`}>{top}</span>
        </div>
      );
    }
    // если market1IsDex но мы рендерим asks2/bids2 — обычное поведение дальше
  }

  // Обычный путь — для всех остальных случаев
  if (isAsks) {
    arr.sort((a,b) => (parseFloat(a[0]||0) - parseFloat(b[0]||0)));
  } else {
    arr.sort((a,b) => (parseFloat(b[0]||0) - parseFloat(a[0]||0)));
  }

  const limit = parseInt(depthGlass || 3, 10);
  const limited = arr.slice(0, limit);
  while (limited.length < limit) limited.push([0,0]);

  const toRender = isAsks ? limited.slice().reverse() : limited;

  return toRender.map((item, index) => {
    const price = item[0] ?? 0;
    const volume = item[1] ?? 0;
    return (
      <div className={`market-container-graph ${isAsks ? 'asks' : 'bids'}`} key={`${marketName}-${index}`}>
        <span className={`price ${checkPriceChange(price)}`}>{price}</span>
        <span className={`volume ${checkVolumeChange(volume)}`}>{formatNumber(Number(volume)) || '0'}$</span>
      </div>
    );
  });
};





  // Проверка на изменение цены для анимации
  const checkPriceChange = (currentPrice) => {
    if (previousData && previousData.price !== currentPrice) {
      setPreviousData({ ...previousData, price: currentPrice });
      return 'flicker'; // Анимация для изменений
    }
    return '';
  };

  // Проверка на изменение объема для анимации
  const checkVolumeChange = (currentVolume) => {
    if (previousData && previousData.volume !== currentVolume) {
      setPreviousData({ ...previousData, volume: currentVolume });
      return 'flicker'; // Анимация для изменений
    }
    return '';
  };

  // Форматирование числа для отображения
  const formatNumber = (number) => {
    if (number >= 1000000) {
      return (number / 1000000).toFixed(1) + 'M';
    }
     else if (number >= 1000) {
      return (number / 1000).toFixed(1) + 'K';
    } 
    else {
      return number.toFixed(0);
    }
  };

  // ---------- ADD START: helpers for normalization and effective price ----------
/**
 * amountToUSD(price, amount, multiplier)
 * multiplier: если контрактная биржа — usdPerContract (из multipliers), иначе undefined/null
 */
function amountToUSD(price, amount, multiplier) {
  if (!price || !amount) return 0;
  if (multiplier) {
    return amount * multiplier;
  } else {
    return price * amount;
  }
}

/**
 * calculateEffectivePrice: JS port вашей Python-функции.
 * order_book: [[price, amountUSD], ...] — amount уже должны быть в USD (входящие данные нормализуем)
 * trade_quantity: сумма в USD
 * возвращает effective price (float) или null
 */
/**
 * calculateEffectivePriceJS — faithful port of Python calculate_effective_price
 * order_book: [[price, amountUSD], ...]  (amount already in USD)
 * trade_quantity: сумма в USD
 * returns effective price (number) or null
 */
function calculateEffectivePriceJS(order_book, trade_quantity) {
  try {
    if (!Array.isArray(order_book) || order_book.length === 0) return null;
    const qty = Number(trade_quantity);
    if (!isFinite(qty) || qty <= 0) return null;

    let total_cost = 0;
    let total_volume = 0;
    let remaining = qty;

    for (let i = 0; i < order_book.length; i++) {
      const row = order_book[i];
      if (!Array.isArray(row) || row.length < 2) return null;

      const price = Number(row[0]);
      const amountUsd = Number(row[1]); // amount already in USD

      // strict validation: if parsing failed or price <= 0 -> behave like Python (error -> None)
      if (!isFinite(price) || !isFinite(amountUsd)) return null;
      if (price <= 0 || amountUsd < 0) return null;

      if (remaining <= amountUsd) {
        const partial_volume = remaining / price; // base units
        total_cost += remaining;
        total_volume += partial_volume;
        // if total_volume == 0 -> return null (like Python)
        return total_volume ? (total_cost / total_volume) : null;
      } else {
        total_cost += amountUsd;
        total_volume += amountUsd / price;
        remaining -= amountUsd;
      }
    }

    // if we've exhausted order_book and still have remaining => not enough depth
    return null;
  } catch (err) {
    // mirror Python: any exception -> None
    return null;
  }
}

/**
 * Когда одна из сторон — DEX: рассчитываем effective только по nonDex стороне (depthUsd),
 * а для DEX используем top-of-book цены.
 *
 * obDex   - orderbook объекта DEX (asks/bids arrays)
 * obNon   - orderbook не-DEX биржи
 * depthUsd - глубина в USD
 * dexIsFirst - true если DEX — это ob1 (первая сторона), false если DEX — вторая сторона
 *
 * Возвращает { effInVal, effOutVal } где значения либо number либо null
 */
function computeEffectiveWhenOneDex(obDex, obNon, depthUsd, dexIsFirst) {
  try {
    if (!obDex || !obNon) return { effInVal: null, effOutVal: null };
    if (!Array.isArray(obDex.asks) || !Array.isArray(obDex.bids)) return { effInVal: null, effOutVal: null };

    // effective по non-dex (как раньше)
    const effective_asks_non = calculateEffectivePriceJS(obNon.asks, depthUsd);
    const effective_bids_non = calculateEffectivePriceJS(obNon.bids, depthUsd);

    const top_ask_dex = (obDex.asks && obDex.asks.length) ? Number(obDex.asks[0][0]) : null;
    const top_bid_dex = (obDex.bids && obDex.bids.length) ? Number(obDex.bids[0][0]) : null;

    let eff_in = null, eff_out = null;

    if (dexIsFirst) {
      // original: eff_in = (effective_bids2 / effective_asks1) - 1
      // here: effective_asks1 absent -> use top_ask_dex
      if (effective_bids_non != null && top_ask_dex != null) {
        eff_in = ((effective_bids_non / top_ask_dex) - 1) * 100;
      }
      // original: eff_out = (effective_asks2 / effective_bids1) - 1
      // here: effective_bids1 absent -> use top_bid_dex
      if (effective_asks_non != null && top_bid_dex != null) {
        eff_out = ((effective_asks_non / top_bid_dex) - 1) * 100;
      }
    } else {
      // dex is second
      // original eff_in = effective_bids2 / effective_asks1 -> replace effective_bids2 with top_bid_dex
      if (effective_asks_non != null && top_bid_dex != null) {
        eff_in = ((top_bid_dex / effective_asks_non) - 1) * 100;
      }
      // eff_out = effective_asks2 / effective_bids1 -> replace effective_asks2 with top_ask_dex
      if (effective_bids_non != null && top_ask_dex != null) {
        eff_out = ((top_ask_dex / effective_bids_non) - 1) * 100;
      }
    }

    const effInVal = eff_in === null ? null : Number(eff_in.toFixed(2));
    const effOutVal = eff_out === null ? null : Number(eff_out.toFixed(2));
    return { effInVal, effOutVal };
  } catch (e) {
    console.error('computeEffectiveWhenOneDex error', e);
    return { effInVal: null, effOutVal: null };
  }
}


function computeEffectiveWithDepth(depthUsd) {
  try {
    const ob1 = latestOrderbooksRef.current.c1;
    const ob2 = latestOrderbooksRef.current.c2;
    if (!ob1 || !ob2) {
      // если стаканы ещё не пришли — оставляем effective null
      setData(prev => prev ? ({ ...prev, effective_in: null, effective_out: null }) : prev);
      setEffective_in(null);
      setEffective_out(null);
      return;
    }

    // top book как раньше
    const hasTopIn = Array.isArray(ob2.bids) && ob2.bids.length > 0 && Array.isArray(ob1.asks) && ob1.asks.length > 0;
    const hasTopOut = Array.isArray(ob2.asks) && ob2.asks.length > 0 && Array.isArray(ob1.bids) && ob1.bids.length > 0;
    const top_in = hasTopIn ? (((parseFloat(ob2.bids[0][0]) / parseFloat(ob1.asks[0][0])) - 1) * 100) : 'wait';
    const top_out = hasTopOut ? (((parseFloat(ob2.asks[0][0]) / parseFloat(ob1.bids[0][0])) - 1) * 100) : 'wait';
    const inValue = top_in === 'wait' ? 'wait' : Number(top_in.toFixed(2));
    const outValue = top_out === 'wait' ? 'wait' : Number(top_out.toFixed(2));

    let effInVal = null;
    let effOutVal = null;

    if (depthUsd > 0) {
      try {
        const m1 = (String(market1 || '').toLowerCase() === 'dex');
        const m2 = (String(market2 || '').toLowerCase() === 'dex');

        if (m1 && !m2) {
          // если первая сторона DEX — считаем effective только по второй (non-dex),
          // а для dex используем top-of-book (см. helper)
          const res = computeEffectiveWhenOneDex(ob1, ob2, depthUsd, true);
          effInVal = res.effInVal;
          effOutVal = res.effOutVal;
        } else {
          // ни одна или обе стороны не DEX — прежняя логика (оба effective)
          const effective_asks1 = calculateEffectivePriceJS(ob1.asks, depthUsd);
          const effective_bids1 = calculateEffectivePriceJS(ob1.bids, depthUsd);
          const effective_asks2 = calculateEffectivePriceJS(ob2.asks, depthUsd);
          const effective_bids2 = calculateEffectivePriceJS(ob2.bids, depthUsd);

          let eff_in = null, eff_out = null;
          if (effective_bids2 != null && effective_asks1 != null) eff_in = ((effective_bids2 / effective_asks1) - 1) * 100;
          if (effective_asks2 != null && effective_bids1 != null) eff_out = ((effective_asks2 / effective_bids1) - 1) * 100;

          effInVal = eff_in === null ? null : Number(eff_in.toFixed(2));
          effOutVal = eff_out === null ? null : Number(eff_out.toFixed(2));
        }
      } catch (e) {
        console.error("computeEffectiveWithDepth: effective calc failed", e);
        effInVal = null;
        effOutVal = null;
      }
    }

    const dataObj = {
      type: "constant",
      in: inValue,
      out: outValue,
      effective_in: effInVal,
      effective_out: effOutVal,
      depth: depthUsd,
      asks1: Array.isArray(ob1.asks) ? ob1.asks.slice(0, 50) : [],
      bids1: Array.isArray(ob1.bids) ? ob1.bids.slice(0, 50) : [],
      asks2: Array.isArray(ob2.asks) ? ob2.asks.slice(0, 50) : [],
      bids2: Array.isArray(ob2.bids) ? ob2.bids.slice(0, 50) : [],
      sp_or_ft: spOrFt,
      time: new Date().toISOString()
    };

    setData(dataObj);
    setHasSubscribe(true);
    setEntrySpread(inValue);
    setExitSpread(outValue);
    setEffective_in(effInVal);
    setEffective_out(effOutVal);
    setTime(new Date().toLocaleTimeString());
  } catch (err) {
    console.error("computeEffectiveWithDepth error", err);
  }
}



// recompute effective prices from latestOrderbooksRef and current debouncedDepth
function recomputeEffectiveFromLatest() {
  try {
    const ob1 = latestOrderbooksRef.current.c1;
    const ob2 = latestOrderbooksRef.current.c2;
    if (!ob1 || !ob2) return; // если одного из стаканов нет — нечего собирать

    const depthUsd = parseFloat(debouncedDepth.current || 0) || 0;

    // --- top-of-book (всегда вычисляем, даже если useDepth=false) ---
    const hasTopIn = Array.isArray(ob2.bids) && ob2.bids.length > 0 && Array.isArray(ob1.asks) && ob1.asks.length > 0;
    const hasTopOut = Array.isArray(ob2.asks) && ob2.asks.length > 0 && Array.isArray(ob1.bids) && ob1.bids.length > 0;
    const top_in = hasTopIn ? (((parseFloat(ob2.bids[0][0]) / parseFloat(ob1.asks[0][0])) - 1) * 100) : 'wait';
    const top_out = hasTopOut ? (((parseFloat(ob2.asks[0][0]) / parseFloat(ob1.bids[0][0])) - 1) * 100) : 'wait';

    const inValue = top_in === 'wait' ? 'wait' : Number(top_in.toFixed(2));
    const outValue = top_out === 'wait' ? 'wait' : Number(top_out.toFixed(2));

    let effInVal = null;
    let effOutVal = null;

    if (depthUsd > 0) {
      try {
        const m1 = (String(market1 || '').toLowerCase() === 'dex');
        const m2 = (String(market2 || '').toLowerCase() === 'dex');

        if (m1 && !m2) {
          const res = computeEffectiveWhenOneDex(ob1, ob2, depthUsd, true);
          effInVal = res.effInVal;
          effOutVal = res.effOutVal;
        } else {
          const effective_asks1 = calculateEffectivePriceJS(ob1.asks, depthUsd);
          const effective_bids1 = calculateEffectivePriceJS(ob1.bids, depthUsd);
          const effective_asks2 = calculateEffectivePriceJS(ob2.asks, depthUsd);
          const effective_bids2 = calculateEffectivePriceJS(ob2.bids, depthUsd);

          let eff_in = null, eff_out = null;
          if (effective_bids2 != null && effective_asks1 != null) eff_in = ((effective_bids2 / effective_asks1) - 1) * 100;
          if (effective_asks2 != null && effective_bids1 != null) eff_out = ((effective_asks2 / effective_bids1) - 1) * 100;

          effInVal = eff_in === null ? null : Number(eff_in.toFixed(2));
          effOutVal = eff_out === null ? null : Number(eff_out.toFixed(2));
        }
      } catch (e) {
        console.error("recomputeEffectiveFromLatest: effective calc failed", e);
        effInVal = null;
        effOutVal = null;
      }
    }

    const dataObj = {
      type: "constant",
      in: inValue,
      out: outValue,
      effective_in: effInVal,
      effective_out: effOutVal,
      depth: depthUsd,
      asks1: Array.isArray(ob1.asks) ? ob1.asks.slice(0, 50) : [],
      bids1: Array.isArray(ob1.bids) ? ob1.bids.slice(0, 50) : [],
      asks2: Array.isArray(ob2.asks) ? ob2.asks.slice(0, 50) : [],
      bids2: Array.isArray(ob2.bids) ? ob2.bids.slice(0, 50) : [],
      sp_or_ft: spOrFt,
      time: new Date().toISOString()
    };

    setData(dataObj);
    setHasSubscribe(true);
    setEntrySpread(inValue);
    setExitSpread(outValue);
    setEffective_in(effInVal);
    setEffective_out(effOutVal);
    setTime(new Date().toLocaleTimeString());
  } catch (err) {
    console.error("recomputeEffectiveFromLatest error", err);
  }
}


function resolveMultiplier(rawMultiplier, payloadSymbol) {
  if (rawMultiplier == null) return 1;
  if (typeof rawMultiplier === 'number') return Number(rawMultiplier) || 1;
  if (typeof rawMultiplier === 'string' && !isNaN(Number(rawMultiplier))) return Number(rawMultiplier);

  if (typeof rawMultiplier === 'object') {
    const tried = [];
    if (payloadSymbol) {
      tried.push(payloadSymbol);
      tried.push(payloadSymbol.replace(/_/g, ''));
      tried.push(payloadSymbol.toUpperCase());
      tried.push(payloadSymbol.toUpperCase().replace(/_/g, ''));
    }
    tried.push('multiplier', 'value', 'usdPerContract', 'contractSize');

    for (const k of tried) {
      if (k && (rawMultiplier[k] !== undefined && rawMultiplier[k] !== null)) {
        const v = Number(rawMultiplier[k]);
        if (!isNaN(v)) return v;
      }
    }
    // try any numeric value in object
    for (const k of Object.keys(rawMultiplier)) {
      const v = Number(rawMultiplier[k]);
      if (!isNaN(v)) return v;
    }
  }
  return 1;
}

async function onOrderbookReceived(payload, idx) {
  try {
    const market = (payload.market || '').toLowerCase();

    // gateio throttling
    if (market === 'gateio') {
      const now = Date.now();
      const lastKey = idx === 1 ? 'gateioC1' : 'gateioC2';
      if (now - (lastProcessedRef.current[lastKey] || 0) < 80) return;
      lastProcessedRef.current[lastKey] = now;
    }

    let rawMultiplier = idx === 1 ? multiplier1Ref.current : multiplier2Ref.current;
    

    if (rawMultiplier == null) {
      
      rawMultiplier = localMultipliers?.[market]?.[payload.symbol.replace('_', '').replace('-', '')] || null;
   //   console.log('offline_mult', payload.symbol, rawMultiplier, localMultipliers, market);
    }
    const resolvedMultiplier = resolveMultiplier(rawMultiplier, payload.symbol);
    // determine if this side is futures
    const thisSideIsFutures = (spOrFt === 'futures') || (spOrFt === 'spot' && idx === 2);

    // normalize and convert to [price, amountUsd]
    const normUsd = (arr) => {
      if (!Array.isArray(arr)) return [];
      return arr.map(it => {
        let p = 0, q = 0, maybeUsd = null;

        if (Array.isArray(it)) {
          // typical forms: [price, size] or [price, size, ...] or [price, amountUsd]
          p = parseFloat(it[0]) || 0;
          q = parseFloat(it[1]) || 0;
          // if there's a third element that looks like usd -> use it
          if (it.length >= 3) {
            const third = Number(it[2]);
            if (!isNaN(third)) {
              maybeUsd = third;
            }
          }
        } else if (it && typeof it === 'object') {
          p = parseFloat(it.price ?? it.p ?? Object.values(it)[0]) || 0;
          q = parseFloat(it.size ?? it.s ?? it.amount ?? Object.values(it)[1]) || 0;
        } else {
          return null;
        }


        
        // Some feeds may supply array [price, amountUsd] directly (rare) — detect: if q is large and equals approx p*q ??? can't be exact
        // We'll use rule: if thisSideIsFutures AND resolvedMultiplier > 1 => treat q as contracts -> USD = q * resolvedMultiplier
        // else: spot: USD = p * q
        let amountUsd;
        if (thisSideIsFutures && market != 'lbank') {
          if (resolvedMultiplier) {
            amountUsd = q * Number(resolvedMultiplier) * p;
         //   console.info('normUsd: applied multiplier', idx, resolvedMultiplier, 'for', payload.symbol, 'q=', q, '-> usd=', amountUsd);
          } else {
            // no meaningful multiplier: maybe server already sent USD as q (fallback)
            // Try heuristic: if p * q is very different from q, assume q is contracts -> fallback to p*q to avoid zero:
            amountUsd = p * q;
         //   console.info('normUsd: fallback futures p*q used for', payload.symbol, 'p=', p, 'q=', q, '-> usd=', amountUsd);
          }
        } else {
          // spot
          amountUsd = p * q;
        }

        return [p, amountUsd];
      }).filter(Boolean);
    };

    const asksNorm = normUsd(payload.asks || []);
    const bidsNorm = normUsd(payload.bids || []);

    asksNorm.sort((a, b) => parseFloat(a[0] || 0) - parseFloat(b[0] || 0));
    bidsNorm.sort((a, b) => parseFloat(b[0] || 0) - parseFloat(a[0] || 0));
    
    latestOrderbooksRef.current[`c${idx}`] = {
      market: payload.market,
      symbol: payload.symbol,
      asks: asksNorm,
      bids: bidsNorm,
      timestamp: payload.timestamp || Date.now()
    };

    const ob1 = latestOrderbooksRef.current.c1;
    const ob2 = latestOrderbooksRef.current.c2;

    if (ob1 && ob2) {
      recomputeEffectiveFromLatest();
      return;
    }

    const partial = {
      type: "constant",
      in: "wait",
      out: "wait",
      effective_in: null,
      effective_out: null,
      depth: debouncedDepth.current || 0,
      asks1: idx === 1 ? asksNorm.slice(0, 50) : [[0,0]],
      bids1: idx === 1 ? bidsNorm.slice(0, 50) : [[0,0]],
      asks2: idx === 2 ? asksNorm.slice(0, 50) : [[0,0]],
      bids2: idx === 2 ? bidsNorm.slice(0, 50) : [[0,0]],
      sp_or_ft: spOrFt,
      time: new Date().toISOString()
    };
    setData(partial);
    setEntrySpread("wait");
    setExitSpread("wait");
    setEffective_in(null);
    setEffective_out(null);
    setTime(new Date().toLocaleTimeString());
  } catch (e) {
    console.error("onOrderbookReceived error", e);
  }
}

useEffect(() => {
  // всегда пробуем пересчитать по последним наличным стаканам;
  // recomputeEffectiveFromLatest умеет и top и effective
  recomputeEffectiveFromLatest();
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [debouncedDepth.current, useDepth]);

async function startConnector(index) {
  const market = index === 1 ? market1 : market2;
  const coinSymbolRaw = index === 1
    ? debouncedCoin
    : (showCoin2 ? (debouncedCoin2 || debouncedCoin) : debouncedCoin);

  if (!market || !coinSymbolRaw) return;

    // --- LBank tiny-wait: don't start connector until multipliers arrived (max 500ms)
    // reason: LBank requires multiplier present; starting earlier causes wrong normalization/subscribe
    try {
      const mktLower = String(market || '').toLowerCase();
      if (mktLower === 'lbank') {
        const mulRefKey = (index === 1) ? 'multiplier1Ref' : 'multiplier2Ref';
        let hasMul = (index === 1) ? multiplier1Ref.current : multiplier2Ref.current;
        if (hasMul == null) {
      
        hasMul = localMultipliers?.[market]?.[coinSymbolRaw.replace('_', '').replace('-', '')] || null;
   //   console.log('offline_mult', payload.symbol, rawMultiplier, localMultipliers, market);
        }
        // if multiplier not yet present — schedule small polling retry and return
        if (hasMul == null) {

          // avoid duplicating retry intervals for same connector
          const key = `c${index}`;
          const rec = connectorsRef.current[key] || (connectorsRef.current[key] = {});
          if (rec._lbankRetryId) {
            // already retrying — no-op
            return;
          }
          const MAX_WAIT = 500; // ms total
          const TICK = 50; // ms between checks
          let waited = 0;
          rec._lbankRetryId = setInterval(() => {
            const readyMul = (index === 1) ? multiplier1Ref.current : multiplier2Ref.current;
            if (readyMul != null || waited >= MAX_WAIT) {
              clearInterval(rec._lbankRetryId);
              rec._lbankRetryId = null;
              // try starting again (will use current mul if available)
              try { startConnector(index); } catch(e) { console.warn('startConnector retry failed', e); }
            }
            waited += TICK;
          }, TICK);
          // return now — actual start will happen from retry callback
          return;
        }
      }
    } catch (e) {
      console.warn('LBank wait logic failed (continuing startConnector):', e);
    }

  // mode / formatted symbol
  let modeForExchange;
  if (spOrFt === 'futures') modeForExchange = 'futures';
  else if (spOrFt === 'spot') modeForExchange = (index === 1) ? 'spot' : 'futures';
  else modeForExchange = spOrFt === 'futures' ? 'futures' : 'spot';

  const formattedSymbol = formatSymbolForExchange(market, coinSymbolRaw, modeForExchange);

  // early-skip if same
  try {
    const saved = connectorsRef.current[`c${index}`];
    if (saved && saved.meta) {
      const sameMarket = saved.meta.market === market;
      const sameSymbol = saved.meta.formattedSymbol === formattedSymbol;
      const sameMode = saved.meta.mode === modeForExchange;
      if (sameMarket && sameSymbol && sameMode) {
        // only update token if connector supports it
        if (saved.inst && typeof saved.inst.setToken === 'function' && kucoinTokenState) {
          try { saved.inst.setToken(kucoinTokenState); } catch(e) {}
        }
        console.debug(`startConnector(${index}) — skip reconnect (same meta)`);
        return;
      }
    }
  } catch (e) {
    console.warn('startConnector: early check failed', e);
  }


  // mark UI as reconnecting: clear data so UI shows '-' / empty
  if (market1 == 'Dex')
  {
    try {
        latestOrderbooksRef.current[`c${index}`] = null;
        setData(null);
        setEffective_in(null);
        setEffective_out(null);
        setTime('');
      } catch (e) { /* ignore */ }
  } else {
      latestOrderbooksRef.current[`c${index}`] = null;
     // setData(null);
        setEntrySpread(null);
        setExitSpread(null);
        setEffective_in(null);
        setEffective_out(null);
        setTime('');
      setTimeout(() => {
        latestOrderbooksRef.current[`c${index}`] = null;
     // setData(null);
        setEntrySpread(null);
        setExitSpread(null);
        setEffective_in(null);
        setEffective_out(null);
        setTime('');
      }, 50)
      setTimeout(() => {
        latestOrderbooksRef.current[`c${index}`] = null;
     // setData(null);
        setEntrySpread(null);
        setExitSpread(null);
        setEffective_in(null);
        setEffective_out(null);
        setTime('');
      }, 100)
      
  }
  // stop previous
  try { stopConnector(index); } catch (e) {}

  
   
  

  // If market is Dex -> subscribe via server socket (simple interval retry)
if ((market || '').toLowerCase() === 'dex') {
  try {
    const key = `c${index}`;
    // create connector record (store retry id + tries)
    connectorsRef.current[key] = {
      inst: null,
      unsubscribe: () => {
        try {
          if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
            socketRef.current.send(JSON.stringify({ action: "dex_unsubscribe", symbol: formattedSymbol }));
          }
        } catch (e) { console.warn('dex_unsubscribe failed', e); }
      },
      meta: { market, formattedSymbol, mode: modeForExchange },
      // control fields for retry
      _dexRetryId: null,
      _dexTries: 0,
    };

    const MAX_TRIES = 30;
    const INTERVAL_MS = 200;

    const trySend = () => {
      const rec = connectorsRef.current[key];
      if (!rec) return; // might be stopped meanwhile

      // if already given up
      if (rec._dexTries >= MAX_TRIES) {
        if (rec._dexRetryId) { clearInterval(rec._dexRetryId); rec._dexRetryId = null; }
        console.warn(`[DEX] gave up subscribe ${formattedSymbol} after ${rec._dexTries} tries`);
        return;
      }

      // If socket open — send subscribe
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        try {
          socketRef.current.send(JSON.stringify({ action: "dex_subscribe", symbol: formattedSymbol }));
          // we sent — cancel retry interval (server will ack separately)
          if (rec._dexRetryId) { clearInterval(rec._dexRetryId); rec._dexRetryId = null; }
          // mark one successful send attempt so we don't loop unnecessarily
          rec._dexSubscribed = true;
          rec._dexTries = MAX_TRIES; // prevent further attempts
          console.info(`[DEX] sent subscribe for ${formattedSymbol}`);
        } catch (err) {
          rec._dexTries = (rec._dexTries || 0) + 1;
          console.warn('[DEX] subscribe send failed, will retry', err);
        }
      } else {
        // socket not open yet — increase tries and wait for next tick
        rec._dexTries = (rec._dexTries || 0) + 1;
      }
    };

    // If socket already open — try immediate send, else start interval
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      trySend();
    } else {
      const id = setInterval(trySend, INTERVAL_MS);
      connectorsRef.current[key]._dexRetryId = id;
      // Also try once immediately (so we don't always wait for first tick)
      trySend();
    }
    dexSubscriptionsRef.current.add(formattedSymbol);
    return;
  } catch (e) {
    console.error('startConnector (DEX) error', e);
    connectorsRef.current[`c${index}`] = null;
    return;
  }
}


  // Otherwise — normal createConnector flow (CEX)
  const mul1 = multiplier1Ref.current;
  const mul2 = multiplier2Ref.current;
  const opts = {
    token: kucoinTokenState || undefined,
    mode: modeForExchange,
    throttleMs: (market || '').toLowerCase() === 'gateio' ? 100 : undefined,
    symbolOverride: formattedSymbol,
    multiplier1: mul1,
    multiplier2: mul2,
    index: index
  };

  let conn = null;
  try {
    conn = createConnector(market, formattedSymbol, opts);
    if (!conn) throw new Error('createConnector returned falsy');

    connectorsRef.current[`c${index}`] = { inst: conn, unsubscribe: null, meta: { market, formattedSymbol, mode: modeForExchange } };

    const onData = (payload) => {
      try { onOrderbookReceived(payload, index); } catch (e) { console.error('onData callback error', e); }
    };

    if (typeof conn.setToken === 'function' && kucoinTokenState) {
      try { conn.setToken(kucoinTokenState); } catch (e) { console.warn('conn.setToken failed', e); }
    }

    if (typeof conn.connect === 'function') {
      try { conn.connect(); } catch (e) { console.warn('conn.connect threw', e); }
    }

    if (typeof conn.subscribe === 'function') {
      try {
        const maybeUnsub = conn.subscribe(onData, { symbolOverride: formattedSymbol });
        if (typeof maybeUnsub === 'function') connectorsRef.current[`c${index}`].unsubscribe = maybeUnsub;
      } catch (e) {
        // retry once
        try {
          if (typeof conn.connect === 'function') conn.connect();
          const maybeUnsub2 = conn.subscribe(onData, { symbolOverride: formattedSymbol });
          if (typeof maybeUnsub2 === 'function') connectorsRef.current[`c${index}`].unsubscribe = maybeUnsub2;
        } catch (errRetry) {
          console.error('subscribe/connect retry failed', errRetry);
          throw errRetry;
        }
      }
    } else {
      connectorsRef.current[`c${index}`].unsubscribe = null;
    }

    return;
  } catch (e) {
    console.error('startConnector error', e);
    // cleanup fallback
    try {
      const savedNow = connectorsRef.current[`c${index}`];
      if (savedNow && savedNow.inst) {
        try { if (typeof savedNow.unsubscribe === 'function') savedNow.unsubscribe(); } catch (_) {}
        try { if (typeof savedNow.inst.close === 'function') savedNow.inst.close(); } catch (_) {}
      }
    } catch (cleanupErr) {
      console.warn('cleanup failed', cleanupErr);
    } finally {
      connectorsRef.current[`c${index}`] = null;
    }

    // fallback -> прокси через сервер (если socket открыт)
    try {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify({ action: "proxy_request", market, symbol: coinSymbolRaw }));
      }
    } catch (errProxy) { console.error('proxy_request failed', errProxy); }
  }
}

// ----- REPLACE stopConnector -----
function stopConnector(index) {
  try {
    const saved = connectorsRef.current[`c${index}`];
    if (saved) {
      try {
        if (saved && saved._dexRetryId) {
          clearInterval(saved._dexRetryId);
          saved._dexRetryId = null;
        }
      } catch (e) { /* ignore */ }
      // unsubscribe function returned by connector.subscribe (CEX)
      try {
        if (typeof saved.unsubscribe === 'function') {
          saved.unsubscribe();
        }
      } catch (e) {
        console.warn('unsubscribe threw', e);
      }

      // instance close (if any)
      try {
        if (saved.inst && typeof saved.inst.close === 'function') {
          saved.inst.close();
        } else if (saved.inst && typeof saved.inst.unsubscribe === 'function') {
          try { saved.inst.unsubscribe(); } catch (e) {}
        }
      } catch (e) {
        console.warn('error closing connector instance', e);
      }

      // if this was Dex (we stored unsubscribe that sends dex_unsubscribe), call it
      try {
        if (!saved.inst && typeof saved.unsubscribe === 'function') {
          saved.unsubscribe();
        }
      } catch (e) { /* ignore */ }

      // If this connector was DEX — remove from desired subscriptions
      try {
        const metaSymbol = saved && saved.meta && saved.meta.formattedSymbol;
        if (metaSymbol && (saved.meta.market || '').toLowerCase() === 'dex') {
          dexSubscriptionsRef.current.delete(metaSymbol);
          // and if socket is open, ask server to unsubscribe
          if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
            socketRef.current.send(JSON.stringify({ action: "dex_unsubscribe", symbol: metaSymbol }));
          }
        }
      } catch(e){/*ignore*/}
      // clear
      connectorsRef.current[`c${index}`] = null;
    }

    // If we previously used server-side DEX subscription - ensure server unsubs
    const market = index === 1 ? market1 : market2;
    const coinSymbolRaw = index === 1 ? debouncedCoin : (debouncedCoin2 || debouncedCoin);
    if ((market || '').toLowerCase() === 'dex') {
      try {
        if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
          socketRef.current.send(JSON.stringify({ action: "dex_unsubscribe", symbol: coinSymbolRaw }));
        }
      } catch (e) { /* ignore */ }
    }
  } catch (e) {
    console.error('stopConnector error', e);
  }
}



// ---- Add this useEffect: propagate kucoinTokenState -> running connectors ----
useEffect(() => {
  // push updated KuCoin token to running connectors (if they support setToken)
  try {
    ['c1', 'c2'].forEach(k => {
      const rec = connectorsRef.current[k];
      if (rec && rec.inst && typeof rec.inst.setToken === 'function') {
        try { rec.inst.setToken(kucoinTokenState); } catch (e) { console.warn('setToken failed for', k, e); }
      }
    });
  } catch (e) {
    console.error('kucoin token propagation error', e);
  }
}, [kucoinTokenState]);


// авто-старты — НЕ закрываем в cleanup, чтобы toggle UI не ломал соединения
useEffect(() => {
  if (!hasSubscribe) {
  //  console.warn("⏸ startConnector(1) пропущен — нет авторизации");
    return;
  }
  startConnector(1);
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [isAuthenticated, market1, debouncedCoin, kucoinTokenState, spOrFt]);

useEffect(() => {
  if (!hasSubscribe) {
  //  console.warn("⏸ startConnector(2) пропущен — нет авторизации");
    return;
  }
  // убрал showCoin2 из deps: переключение UI не вызывает переподключение
  startConnector(2);
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [isAuthenticated, market2, debouncedCoin2, kucoinTokenState, spOrFt]);

useEffect(() => {
  return () => {
    console.debug('Home unmount cleanup: stop all connectors and socket');
    try { stopConnector(1); } catch (e) {}
    try { stopConnector(2); } catch (e) {}
    if (dexKeepaliveRef.current) { clearInterval(dexKeepaliveRef.current); dexKeepaliveRef.current = null; }
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
    try { if (socketRef.current) { socketRef.current.close(); socketRef.current = null; } } catch (e) {}
  };
}, []);


// ---------- ADD END ----------
// ---------- ADD START: DEX keepalive ----------
const dexKeepaliveRef = useRef(null);

useEffect(() => {
  // when we have DEX subscription (market1 or market2 set to DEX and socket open), send keepalive every 6s
  const enableKeepalive = () => {
    if (dexKeepaliveRef.current) clearInterval(dexKeepaliveRef.current);
    dexKeepaliveRef.current = setInterval(() => {
      try {
        if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
          // send dex_keepalive for active dex symbol(s)
          if ((market1 || '').toLowerCase() === 'dex') {
            socketRef.current.send(JSON.stringify({ action: "dex_keepalive", symbol: debouncedCoin + 'USDT' }));
          }
          if ((market2 || '').toLowerCase() === 'dex' && showCoin2) {
            socketRef.current.send(JSON.stringify({ action: "dex_keepalive", symbol: debouncedCoin + 'USDT' }));
          }
        }
      } catch (e) { /* ignore */ }
    }, 5000);
  };

  enableKeepalive();
  return () => {
    if (dexKeepaliveRef.current) clearInterval(dexKeepaliveRef.current);
    dexKeepaliveRef.current = null;
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [socketRef.current, market1, market2, debouncedCoin, debouncedCoin2, showCoin2]);




  // Функция для расчета и отображения спреда
  const calculateSpread = () => {
    if (data && (data.in != 'Error' && data.out != 'wait') || (data && (data.in == 0 || data.out == 0))) {
      let entrySpread; // Спред для входа
      let exitSpread; // Спред для выхода
      if (useDepth) {
        entrySpread = parseFloat(data.effective_in).toFixed(2); // Спред для входа
        exitSpread = parseFloat(data.effective_out).toFixed(2);
        if (entrySpread == null) {
          entrySpread = 'VAL';
          exitSpread = 'VAL'
        }
      } else {
        entrySpread = parseFloat(data.in).toFixed(2); // Спред для входа
        exitSpread = parseFloat(data.out).toFixed(2); // Спред для выхода
      }
    
     // const entrySpreadColor = entrySpread > 0 ? 'spread-green' : entrySpread < 0 ? 'spread-red' : ''; // Зеленый для положительного, красный для отрицательного
     // const exitSpreadColor = exitSpread > 0 ? 'spread-green' : exitSpread < 0 ? 'spread-red' : ''; // Зеленый для положительного, красный для отрицательного
     // Убедимся, что 0 выводится корректно, а не "-"
    // console.log(entrySpread)
  //  console.log(entrySpread)
     entrySpread = entrySpread == 0 ? '0.00%' : (entrySpread + '%');
     exitSpread = exitSpread == 0 ? '0.00%' : (exitSpread + '%');
      return (
        <div className="spread-container">
          <div className="spread-item entry">
            <span>{t("spreads.entry")}:</span>
            <span  className={`spread-green value`}>{entrySpread}</span>
          </div>
          <div className="spread-item exit">
            <span>{t("spreads.exit", "Выход")}:</span>
            <span className={`spread-red value`}>{exitSpread}</span>
          </div>
          
        </div>
      );
    }

    return (
      <div className="spread-container">
        <div className="spread-item entry">
          <span>{t("spreads.entry")}</span>
          <span className="value">-</span>
        </div>
        <div className="spread-item exit">
          <span>{t("spreads.exit", "Выход")}</span>
          <span className="value">-</span>
        </div>
       
      </div>
    );
  };

  // Функция для расчета и отображения спреда
  const calculateSpread2 = () => {
    if (data && (data.in != 'Error' && data.out != 'wait') || (data && (data.in == 0 || data.out == 0))) {
      
      
      let entrySpread; // Спред для входа
      let exitSpread; // Спред для выхода
    //  console.log(data.effective_in, isNaN(data.effective_in))
      if (useDepth) {
        entrySpread = data.effective_in == null ? 'VOL' : parseFloat(data.effective_in).toFixed(2);
        exitSpread  = data.effective_out == null ? 'VOL' : parseFloat(data.effective_out).toFixed(2);
      } else {
        entrySpread = parseFloat(data.in).toFixed(2); // Спред для входа
        exitSpread = parseFloat(data.out).toFixed(2); // Спред для выхода
      }
     // const entrySpreadColor = entrySpread > 0 ? 'spread-green' : entrySpread < 0 ? 'spread-red' : ''; // Зеленый для положительного, красный для отрицательного
     // const exitSpreadColor = exitSpread > 0 ? 'spread-green' : exitSpread < 0 ? 'spread-red' : ''; // Зеленый для положительного, красный для отрицательного
     // Убедимся, что 0 выводится корректно, а не "-"
    // console.log(entrySpread)
  //  console.log(entrySpread)
      

     entrySpread = entrySpread == 0 ? '0.00%' : (entrySpread + '%');
     exitSpread = exitSpread == 0 ? '0.00%' : (exitSpread + '%');

  
      return (
        <div className="spread-container-graph">
          <div className="spread-item entry">
            <span>{t("spreads.entry")}:</span>
            <span  className={`spread-green value`}>{entrySpread}</span>
          </div>
          <div className="spread-item exit">
            <span>{t("spreads.exit", "Выход")}:</span>
            <span className={`spread-red value`}>{exitSpread}</span>
          </div>
         
        </div>
      );
    }

    return (
      <div className="spread-container-graph">
        <div className="spread-item entry">
          <span>{t("spreads.entry")}</span>
          <span className="value">-</span>
        </div>
        <div className="spread-item exit">
          <span>{t("spreads.exit", "Выход")}</span>
          <span className="value">-</span>
        </div>
      
      </div>
    );
  };

  if (!authChecked) {
    return <div></div>;  // Можно заменить на спиннер
  }

  // Generate exchange URL for a given market and coin
  // idx: 1 = market1, 2 = market2. When spOrFt === "spot", market2 uses futures URLs.
  const getExchangeUrl = (market, symbol, spOrFt, idx) => {
    if (!market || !symbol) return null;
    const m = market.toLowerCase();
    const cleanSymbol = symbol.replace("USDT", "").toUpperCase();
    // Ensure symbol has USDT suffix for link formatting
    const fullSymbol = cleanSymbol + "USDT";
    const isFutures = spOrFt === "futures";
    // In spot/futures mode: market1 → spot, market2 → futures
    const isSpot = spOrFt === "spot" && idx !== 2;

    const spotUrls = {
      bybit: `https://www.bybit.com/ru-RU/trade/spot/${fullSymbol.replace("USDT", "/USDT")}`,
      mexc: `https://www.mexc.com/ru-RU/exchange/${fullSymbol.replace("USDT", "_USDT")}?_from=search_spot_trade`,
      kucoin: `https://www.kucoin.com/ru/trade/${fullSymbol.replace("USDT", "-USDT")}`,
      gateio: `https://www.gate.io/ru/trade/${fullSymbol.replace("USDT", "_USDT")}`,
      bitget: `https://www.bitget.com/ru/spot/${fullSymbol}`,
      huobi: `https://www.htx.com/trade/${fullSymbol.toLowerCase().replace("usdt", "_usdt")}?type=spot`,
      okx: `https://www.okx.com/ru/trade-spot/${fullSymbol.toLowerCase().replace("usdt", "-usdt")}`,
      binance: `https://www.binance.com/ru/trade/${fullSymbol.replace("USDT", "_USDT")}`,
      bingx: `https://bingx.com/ru-ru/spot/${fullSymbol}/`,
      bitmart: `https://www.bitmart.com/trade/ru-RU?symbol=${fullSymbol.replace("USDT", "_USDT")}`,
      ourbit: `https://www.ourbit.com/ru-RU/exchange/${fullSymbol.replace("USDT", "_USDT")}?_from=search_spot_trade`,
      hyperliquid: `https://app.hyperliquid.xyz/trade/${fullSymbol.replace("USDT", "")}`,
      lbank: `https://www.lbank.com/trade/${fullSymbol.toLowerCase().replace("usdt", "_usdt")}`,
      aster: `https://www.asterdex.com/ru/trade/pro/spot/${fullSymbol}`,
      xt: `https://www.xt.com/ru/trade/${fullSymbol.toLowerCase().replace("usdt", "_usdt")}`,
      weex: `https://www.weex.com/spot/${fullSymbol.replace("USDT", "-USDT")}`,
      phemex: `https://phemex.com/trade/${fullSymbol.replace("USDT", "-USDT")}`,
      coinex: `https://www.coinex.com/ru/exchange/${fullSymbol.replace("USDT", "-USDT").toLowerCase()}`,
    };

    const futuresUrls = {
      bybit: `https://www.bybit.com/trade/usdt/${fullSymbol}`,
      mexc: `https://futures.mexc.com/ru-RU/exchange/${fullSymbol.replace("USDT", "_USDT")}?type=linear_swap`,
      kucoin: `https://www.kucoin.com/ru/futures/trade/${fullSymbol.replace("USDT", "USDTM")}`,
      gateio: `https://www.gate.io/ru/futures/USDT/${fullSymbol.replace("USDT", "_USDT")}`,
      bitget: `https://www.bitget.com/ru/futures/usdt/${fullSymbol}`,
      huobi: `https://www.htx.com/futures/linear_swap/exchange#contract_code=${fullSymbol.replace("USDT", "-USDT")}&contract_type=swap&type=cross`,
      okx: `https://www.okx.com/ru/trade-swap/${fullSymbol.toLowerCase().replace("usdt", "-usdt-swap")}`,
      binance: `https://www.binance.com/ru/futures/${fullSymbol}`,
      bingx: `https://swap.bingx.com/ru-ru/${fullSymbol.replace("USDT", "-USDT")}`,
      bitmart: `https://derivatives.bitmart.com/ru-RU?symbol=${fullSymbol}&theme=dark`,
      ourbit: `https://futures.ourbit.com/ru-RU/exchange/${fullSymbol.replace("USDT", "_USDT")}?type=linear_swap`,
      hyperliquid: `https://app.hyperliquid.xyz/trade/${fullSymbol.replace("USDT", "")}`,
      lbank: `https://www.lbank.com/futures/${fullSymbol.toLowerCase()}`,
      aster: `https://www.asterdex.com/ru/trade/pro/futures/${fullSymbol}`,
      xt: `https://www.xt.com/ru/futures/trade/${fullSymbol.toLowerCase().replace("usdt", "_usdt")}`,
      weex: `https://www.weex.com/futures/${fullSymbol.replace("USDT", "-USDT")}`,
      phemex: `https://phemex.com/futures/${fullSymbol.replace("USDT", "-USDT")}`,
      coinex: `https://www.coinex.com/ru/futures/${fullSymbol.replace("USDT", "-USDT").toLowerCase()}`,
    };

    // For DEX market, use dexScreener like the Telegram bot
    if (m === "dex") {
      // Use the full display symbol for dexscreener search
      return `https://dexscreener.com/search?q=${cleanSymbol}`;
    }

    // For BinanceAlpha
    if (m === "binancealpha") {
      return `https://www.binance.com/en/alpha`;
    }

    const urls = isSpot ? spotUrls : futuresUrls;
    return urls[m] || null;
  };

  // Render exchange name as a clickable link
  const renderMarketLink = (marketName, symbol, spOrFt, idx) => {
    const url = getExchangeUrl(marketName, symbol, spOrFt, idx);
    if (url) {
      return (
        <a href={url} target="_blank" rel="noopener noreferrer" className="market-link-exchange" title={`Открыть ${marketName}`}>
          {marketName}
        </a>
      );
    }
    return marketName;
  };

  return (
    <div>
    {hasSubscribe === null ? (
        // пока не решили — показываем красивый спиннер загрузки
        <div className="loading-center-container">
          <div className="loader" aria-label="loading"></div>
          <div>{t("trade.connect")}</div>
        </div>
      ) : hasSubscribe === false ? (
            <div className="error-center-container">
            <div className="error-subscription-container">
                <img src="/images/info.svg" alt="Info" className="error-subscription-icon" />
                <div className="error-subscription-text">
                    <h3 className="error-subscription-title">{t("trade.noSubTitle")}</h3>
                    <p className="error-subscription-description">
                        {t("trade.noSubDesc")}
                    </p>
                    <Link to={'/subscription'} className="sub-button">{t("trade.subscription")}</Link>
                </div>
            </div>
            </div>
        ) : (
      <div>
    <div className="home-container">
      <div className="top-bar">

        
        
        {/* Поле ввода монеты с автодополнением */}
        <div className="autocomplete">
          <div style={{ position: 'relative'}}>
          <div style={{ position: 'relative' }} className="coin-input-wrapper">
            {/* Overlay prefix */}
            {String(market1 || '').toLowerCase() === 'dex' && (
              <span className="network-prefix">
                {(coinPrefix || '').padEnd(DEX_NETWORK_LEN).slice(0, DEX_NETWORK_LEN)}
              </span>
            )}
            <input
              type="text"
              // В поле показываем только SUFFIX (чтобы не дублировать префикс)
              value={ String(market1 || '').toLowerCase() === 'dex' ? (coinInputSuffix || '') : (coin || '') }
              onChange={handleCoinInput}
              onKeyDown={handleCoinInputKeyDown}
              onFocus={() => setShowDropdown(true)}
              onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
              className={`coin-input ${String(market1 || '').toLowerCase() === 'dex' ? 'coin-input-with-prefix' : ''}`}
              placeholder={t("trade.coinInput")}
            />
          </div>
          {showDropdown && filteredCoins.length > 0 && (
            <ul className="dropdown">
              {filteredCoins.map((c) => (
                <li key={c} onMouseDown={() => selectCoin(c)}>
                  {c}
                </li>
              ))}
            </ul>
          )}
        </div>
        {/* coin2: видим только если showCoin2 === true */}
        { showCoin2 && (
          <div style={{ marginTop: '15px'}}>
            <input
              type="text"
              value={coin2}
              onChange={(e) => setCoin2(e.target.value.toUpperCase())}
              className="coin-input coin2-input"
              placeholder={t("trade.coinInput2", "Введите монету 2 (BTC, ETH...)")}
              disabled={!showCoin2}
            />
            </div>
        )}
        </div>

        <select value={spOrFt} onChange={handleSpOrFtChange} className="sp-ft-select">
          <option value="futures">{t("trade.futuresFutures")}</option>
          <option value="spot">{t("trade.spotFutures")}</option>
        </select>

      </div>
      <div className="filters-markets">
        {/* Выбор биржи для Market 1 */}
        <select value={market1} onChange={handleMarket1Change} className="market-select">
          <option value="Bybit">Bybit</option>
          <option value="Mexc">Mexc</option>
          <option value="Kucoin">Kucoin</option>
          <option value="Gateio">Gateio</option>
          <option value="Bitget">Bitget</option>
          <option value="Huobi">Huobi</option>
          <option value="Okx">Okx</option>
          <option value="Binance">Binance</option>
          <option value="BingX">BingX</option>
          <option value="BitMart">BitMart</option>
          <option value="Ourbit">Ourbit</option>
          <option value="Hyperliquid">Hyperliquid</option>
          <option value="LBank">LBank</option>
          <option value="Aster">Aster</option>
          <option value="XT">XT</option>
          <option value="CoinEx">CoinEx</option>
          <option value="WEEX">WEEX</option>
          <option value="Phemex">Phemex</option>
          <option value="BinanceAlpha">BinanceAlpha</option>
          <option value="Dex">Dex</option>
          
        </select>
        {/* Выбор биржи для Market 2 */}
        <select value={market2} onChange={handleMarket2Change} className="market-select">
          <option value="Bybit">Bybit</option>
          <option value="Mexc">Mexc</option>
          <option value="Kucoin">Kucoin</option>
          <option value="Gateio">Gateio</option>
          <option value="Bitget">Bitget</option>
          <option value="Huobi">Huobi</option>
          <option value="Okx">Okx</option>
          <option value="Binance">Binance</option>
          <option value="BingX">BingX</option>
          <option value="BitMart">BitMart</option>
          <option value="Ourbit">Ourbit</option>
          <option value="Hyperliquid">Hyperliquid</option>
          <option value="LBank">LBank</option>
          <option value="Aster">Aster</option>
          <option value="XT">XT</option>
          <option value="CoinEx">CoinEx</option>
          <option value="WEEX">WEEX</option>
          <option value="Phemex">Phemex</option>
          <option value="BinanceAlpha">BinanceAlpha</option>
        </select>
        
      </div>
      
    </div>
    <div className={`func-div ${showFuncDiv ? "func-mb" : ""}`}>
      <div className="depth-block">
        <span className="span-value">{t("trade.volume")}$:</span>
        <input 
            type="text" 
            value={depthValue} 
            onChange={handleDepthInput} 
            className="volume-input"
            placeholder="Объём"
          />
        <button onClick={() => changeUseDepth()} className={`toggle-button-depth ${useDepth ? "on" : "off"}`}>
        <span></span>
      </button>
      </div>
      <div className="coin2-toggle-block">
        <button 
          onClick={() => {
            setShowCoin2(prev => {
              if (market1 !== 'Dex')
              {
                const next = !prev;
                if (next) {
                  setCoin2(coin);
                }
                return next;
              } else {
                return prev;
              }
            });
          }}
          className="toggle-button coin2-toggle"
          title={showCoin2 ? "Скрыть дополнительное поле" : "Показать дополнительное поле"}
        
        >
          {showCoin2 ? "-" : "+"}
        </button>
      </div>
      <div>
        <button onClick={() => changeDepth()} className="toggle-button toggle-depth-button">
            {depthGlass == "3" ? "3" : "5"}
        </button>
      </div>
      <div>
         <AlertBell entryPrice={useDepth ? effective_in : entrySpread} exitPrice={useDepth ? effective_out : exitSpread} />
      </div>
    </div>

      {showFuncDiv && (
      <div className="func-div spread-gap">
        {/* Блок для спреда входа */}
  <div className="spread-block">
    <span className="spread-subtitle">{t("spreads.entry")}:</span>
    <div className="spread-input-block ml-spread">
    <input
      type="text"
      value={entryPrice1}
      onChange={(e) => handleInputChange(e, "entryPrice1")}
      className="spread-input"
      placeholder={t("trade.market1")}
    />
    <input
      type="text"
      value={exitPrice1}
      onChange={(e) => handleInputChange(e, "exitPrice1")}
      className="spread-input"
      placeholder={t("trade.market2")}
    />
    </div>
    <button onClick={() => toggleEntrySpread()} className={`toggle-button spread-toggle ml-spread ${useEntrySpread ? "on" : "off"}`}>

      <span></span>
    </button>
  </div>

  {/* Блок для спреда выхода */}
  <div className="spread-block">
  <span className="spread-subtitle ml-0">{t("spreads.exit")}:</span>
    <div className="spread-input-block mr-spread">
    <input
      type="text"
      value={entryPrice2}
      onChange={(e) => handleInputChange(e, "entryPrice2")}
      className="spread-input"
      placeholder={t("trade.market1")}
    />
    <input
      type="text"
      value={exitPrice2}
      onChange={(e) => handleInputChange(e, "exitPrice2")}
      className="spread-input"
      placeholder={t("trade.market2")}
    />
    </div>
    <button onClick={() => toggleExitSpread()} className={`toggle-button spread-toggle ${useExitSpread ? "on" : "off"}`}>

        <span></span>
    </button>

  </div>
      </div>

      )}
    <div className="div-graph">
      {(calculateSpread2()
      )}
      
      <button 
          className={`spread-inner toggle-button ${showFuncDiv ? "active" : ""}`}
          onClick={() => setShowFuncDiv(!showFuncDiv)}
        >
          ⚙️
        </button>
        <button 
          className={`spread-inner-plus toggle-button`}
          onClick={() => {
            openNewTab()
            // if (window.Telegram?.WebApp?.openTelegramLink) {
            //   window.Telegram.WebApp.openTelegramLink("https://t.me/funding_cryptoprojects_bot?startapp=payload");
            // } else {
            //   console.error("Метод openTelegramLink недоступен");
            // }
          }}
        >
          ➕
        </button>
        <SpreadChart key={`${debouncedCoin}-${market1}-${market2}-${spOrFt}-${debouncedCoin2}`} entrySpread={useDepth ? effective_in : entrySpread} exitSpread={useDepth ? effective_out : exitSpread} useEntrySpread={useEntrySpread ? (((exitPrice1 / entryPrice1) - 1) * 100).toFixed(2) : ""} 
  useExitSpread={useExitSpread ? (((exitPrice2 / entryPrice2) -1 ) * 100).toFixed(2) : ""} time={time} coin={coin}/>
        
        {(
        
      <div className={`markets-graph ${depthGlass == "3" ? "" : "x5"}`}>
        <div className="market-graph" >
        <h3>{renderMarketLink(market1, debouncedCoin, spOrFt, 1)}</h3>
          {data ? (
            <>
              {data.asks1 && renderMarket2(data.asks1, 'asks1')}
              {data.bids1 && renderMarket2(data.bids1, 'bids1')}
            </>
          ) : !dataLoaded ? (
            <div>{t("trade.loading")}</div>
          ) : null}
        </div>

        <div className="market-graph">
        <h3>{renderMarketLink(market2, showCoin2 ? debouncedCoin2 : debouncedCoin, spOrFt, 2)}</h3>
          {data ? (
            <>
              {data.asks2 && renderMarket2(data.asks2, 'asks2')}
              {data.bids2 && renderMarket2(data.bids2, 'bids2')}
            </>
          ) : !dataLoaded ? (
            <div>{t("trade.loading")}</div>
          ) : null}
        </div>
      </div>)}
      </div>
      <div className="graph-div2">
      <button 
          className={`history-inner toggle-button ${useZoomGraph2 ? "active" : ""}`}
          onClick={() => setUseZoomGraph2(!useZoomGraph2)}
        >
          🔎
        </button>
      <SpreadChart2 entrySpread={histEntrySpread} exitSpread={histExitSpread} time={histTime} useZoom={useZoomGraph2} />
      </div>
      {error && <div className="error">{error}</div>}
      </div>
        )}
    </div>
  );
};

export default Home;

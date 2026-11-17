// Spreads.js
import React, { useEffect, useState, useRef } from "react";
import { useTranslation } from "react-i18next";
import { fetchFuturesAll, fetchFuturesPage, fetchFuturesId, fetchSpotAll, fetchSpotPage, fetchSpotId, fetchDexAll, fetchDexPage, fetchDexId, fetchChangeToSpread, fetchChangeToCourse, fetchChangeToBig, fetchSettings } from '../api/api.js';
import { Link } from "react-router-dom";
import "./Spreads.css";
import SpreadAlertBell from "./SpreadAlertBell";

export default function Spreads() {
  const { t } = useTranslation();

  const [mode, setMode] = useState(() => localStorage.getItem("mode") ?? "futures");
  useEffect(() => {
    localStorage.setItem("mode", mode);
  }, [mode]);

  const [filterState, setFilterState] = useState(localStorage.getItem("filter") ?? "spread");
  const [entryPositiveState, setEntryPositiveState] = useState(
    JSON.parse(localStorage.getItem("entryPositive") ?? "false")
  );

  // refs — мгновенные значения (для запросов)
  const filter = useRef(filterState);
  const entryPositive = useRef(entryPositiveState);

  // синхронизация state → ref → localStorage
  useEffect(() => {
    filter.current = filterState;
    localStorage.setItem("filter", filterState);
  }, [filterState]);

  useEffect(() => {
    entryPositive.current = entryPositiveState;
    localStorage.setItem("entryPositive", JSON.stringify(entryPositiveState));
  }, [entryPositiveState]);

  const handleEntryPositiveToggle = async () => {
  const newValue = !entryPositive.current; // сразу обновляем ref
  entryPositive.current = newValue;
  setEntryPositiveState(newValue); // обновляем state, чтобы кнопка сразу подсветилась

  // при необходимости сразу обновляем данные
  if (stage === 1) {
    fetchData(1, itemsPerPage);
  } else if (stage === 2 && symbolData) {
    fetchSymbolData(symbolData.symbol, itemsPerPage, symbolPage);
  }
};

const handleFilterChange = async (newFilter) => {
  filter.current = newFilter;   // мгновенно меняем ref
  setFilterState(newFilter);    // обновляем state → UI
  // при необходимости обновляем данные
  if (stage === 1) {
    fetchData(1, itemsPerPage);
  } else if (stage === 2 && symbolData) {
    fetchSymbolData(symbolData.symbol, itemsPerPage, symbolPage);
  }
};

 // const [dataStatus, setDataStatus] = useState("loading"); 
  const dataStatusRef = useRef("loading");

  const [itemsPerPage, setItemsPerPage] = useState(() =>
  parseInt(localStorage.getItem("itemsPerPage") ?? "7", 10)
  );
  useEffect(() => {
    localStorage.setItem("itemsPerPage", itemsPerPage);
  }, [itemsPerPage]);

  const [data, setData] = useState(null);
  const [symbolData, setSymbolData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const searchTimeoutRef = useRef(null);

  const [autoUpdate, setAutoUpdate] = useState(() =>
  JSON.parse(localStorage.getItem("autoUpdate") ?? "true")
  );
  useEffect(() => {
    localStorage.setItem("autoUpdate", JSON.stringify(autoUpdate));
  }, [autoUpdate]);

  const [page, setPage] = useState(1);
  const [symbolPage, setSymbolPage] = useState(1);
  const [transitionLoading, setTransitionLoading] = useState(false);

  // кэш
  const [dataPages, setDataPages] = useState({}); // для главной таблицы
  const [symbolPagesCache, setSymbolPagesCache] = useState({}); // для страниц по символу

  // alerts
  const [futuresThreshold, setFuturesThreshold] = useState(
    localStorage.getItem("futuresThreshold") || ""
  );
  const [spotThreshold, setSpotThreshold] = useState(
    localStorage.getItem("spotThreshold") || ""
  );
  const [dexThreshold, setDexThreshold] = useState(
    localStorage.getItem("dexThreshold") || ""
  );

  const [futuresEnabled, setFuturesEnabled] = useState(
    false
  );
  const [spotEnabled, setSpotEnabled] = useState(
    false
  );
  const [dexEnabled, setDexEnabled] = useState(
    JSON.parse(localStorage.getItem("dexEnabled") ?? "false")
  );
   const [blacklistAlert, setBlacklistAlert] = useState(
      localStorage.getItem("blacklistAlert")?.split(",").map(s => s.trim()).filter(Boolean) || []
    );
   useEffect(() => {
      localStorage.setItem("futuresThreshold", futuresThreshold);
    }, [futuresThreshold]);
  
    useEffect(() => {
      localStorage.setItem("spotThreshold", spotThreshold);
    }, [spotThreshold]);
  
    useEffect(() => {
      localStorage.setItem("blacklistAlert", blacklistAlert.join(","));
    }, [blacklistAlert]);
  
    useEffect(() => {
      localStorage.setItem("futuresEnabled", futuresEnabled);
    }, [futuresEnabled]);
  
    useEffect(() => {
      localStorage.setItem("spotEnabled", spotEnabled);
    }, [spotEnabled]);

    useEffect(() => {
      localStorage.setItem("dexThreshold", dexThreshold);
    }, [dexThreshold]);

    useEffect(() => {
      localStorage.setItem("dexEnabled", dexEnabled);
    }, [dexEnabled]);

    const [bellData, setBellData] = useState({ itemsFutures: [], itemsSpot: [], itemsDex: [] });

  const intervalRef = useRef(null);


  const pageRef = useRef(page);
  const symbolPageRef = useRef(symbolPage);

  const [stage, setStage] = useState(1); 

  useEffect(() => {
    pageRef.current = page;
  }, [page]);

  useEffect(() => {
    symbolPageRef.current = symbolPage;
  }, [symbolPage]);

  const [idData, setIdData] = useState(null); // для третьего этапа
  const [idLoading, setIdLoading] = useState(false);

  // Helper: returns the API key for the current mode
  const getModeKey = () => {
    if (mode === "futures") return "futures";
    if (mode === "dex") return "dex";
    return "spot";
  };

  const currentItems = data?.pages?.find((p) => p?.page === data?.current_page)?.items ?? [];

    // DEDUPE helper for concurrent fetches
  const inFlightMapRef = useRef(new Map());
  const fetchAllDedupe = async (which /*'futures'|'spot'|'dex'*/, page, items, filterVal, entryPositiveVal) => {
    // ключ по типу + args: чтобы не запускать дубликаты с одинаковыми аргументами
    const key = `${which}|p=${page}|i=${items}|f=${filterVal}|e=${entryPositiveVal ? 1 : 0}`;
    const map = inFlightMapRef.current;

    // если уже есть промис — вернём его (reuse)
    if (map.has(key)) {
      return map.get(key);
    }

    // создаём новый промис и сохраняем
    const p = (async () => {
      try {
        if (which === "futures") {
          return await fetchFuturesAll(page, items, filterVal, entryPositiveVal);
        } else if (which === "dex") {
          return await fetchDexAll(page, items, filterVal, entryPositiveVal);
        } else {
          return await fetchSpotAll(page, items, filterVal, entryPositiveVal);
        }
      } finally {
        // очистим карту после завершения (успех/ошибка)
        // используем setTimeout 0 чтобы избежать race при синхронном повторном вызове в одном цикле
        setTimeout(() => {
          if (map.get(key) === p) map.delete(key);
        }, 0);
      }
    })();

    map.set(key, p);
    return p;
  };


 useEffect(() => {
  let cancelled = false;

  const resetAndLoad = async () => {
    // показываем загрузку
    setTransitionLoading(true);

    // Сбрасываем состояние (всегда на 1-й этап)
    // Обновляем рефы синхронно, чтобы другие функции, читающие pageRef, видели новое значение сразу
    pageRef.current = 1;
    symbolPageRef.current = 1;

    setData(null);
    setSymbolData(null);
    setIdData(null);

    // синхронно ставим стейты страницы (setPage тоже асинхронно, но реф уже корректен)
    setSymbolPage(1);
    setPage(1);

    setDataPages({});
    setSymbolPagesCache({});
    setStage(1);

    try {
     // const res = await fetchData(1, itemsPerPage);
     if (dataStatusRef.current !== 'no_sub')
     {
     const res = await fetchAllDedupe(getModeKey(), 1, itemsPerPage, filter.current, entryPositive.current);
    // setDataStatus(res.status || "loading");
     dataStatusRef.current = res.status || "loading"
      // if (!cancelled) {
      //   setData(res);
      // }
      if (!cancelled && res.status !== 'no_sub') {
        // сохраняем все страницы в кэш

        const newCache = {};
        res.pages.forEach(p => {
          newCache[p.page] = { ...res, pages: [p] };
        });
        setDataPages(newCache);


        // показываем первую страницу
        setData({ ...res, current_page: 1, pages: [res.pages.find(p => p.page === 1)] });

         // 🔔 сразу инициализируем bellData
    // --- формируем данные для колокольчика ---
        let itemsFutures = [];
        let itemsSpot = [];
        let itemsDex = [];

        if (mode === "futures") {
          itemsFutures = [res.pages.find(p => p.page === 1)][0]?.items ?? [];
          if (spotEnabled) {
            const resSpot = await fetchAllDedupe("spot", 1, itemsPerPage, filter.current, entryPositive.current);
            itemsSpot = (resSpot && Array.isArray(resSpot.pages)) ? resSpot.pages.flatMap(p => p.items) : [];
          }
          if (dexEnabled) {
            const resDex = await fetchAllDedupe("dex", 1, itemsPerPage);
            itemsDex = (resDex && Array.isArray(resDex.pages)) ? resDex.pages.flatMap(p => p.items) : [];
          }
        } else if (mode === "spot_futures") {
          itemsSpot = [res.pages.find(p => p.page === 1)][0]?.items ?? [];
          if (futuresEnabled) {
            const resFutures = await fetchAllDedupe("futures", 1, itemsPerPage, filter.current, entryPositive.current);
            itemsFutures = (resFutures && Array.isArray(resFutures.pages)) ? resFutures.pages.flatMap(p => p.items) : [];
          }
          if (dexEnabled) {
            const resDex = await fetchAllDedupe("dex", 1, itemsPerPage);
            itemsDex = (resDex && Array.isArray(resDex.pages)) ? resDex.pages.flatMap(p => p.items) : [];
          }
        } else if (mode === "dex") {
          itemsDex = [res.pages.find(p => p.page === 1)][0]?.items ?? [];
          if (futuresEnabled) {
            const resFutures = await fetchAllDedupe("futures", 1, itemsPerPage, filter.current, entryPositive.current);
            itemsFutures = (resFutures && Array.isArray(resFutures.pages)) ? resFutures.pages.flatMap(p => p.items) : [];
          }
          if (spotEnabled) {
            const resSpot = await fetchAllDedupe("spot", 1, itemsPerPage, filter.current, entryPositive.current);
            itemsSpot = (resSpot && Array.isArray(resSpot.pages)) ? resSpot.pages.flatMap(p => p.items) : [];
          }
        }
        setBellData({ itemsFutures, itemsSpot, itemsDex });
      }
      }
    } catch (err) {
      console.error("Ошибка загрузки данных при смене режима:", err);
    } finally {
      if (!cancelled) {
        setTransitionLoading(false);
      }
    }
  };

  resetAndLoad();
  
  return () => {
    cancelled = true;
  };
}, [mode, itemsPerPage]);

// 🔹 При смене фильтров — мгновенное обновление текущей страницы (stage 1 и 2)
useEffect(() => {
  let cancelled = false;

  const refreshWithFilters = async () => {
    setTransitionLoading(true);

    try {
      // --- Этап 1: главная таблица ---
      if (stage === 1) {
        const res = await fetchAllDedupe(
          getModeKey(),
          pageRef.current,
          itemsPerPage,
          filter.current,
          entryPositive.current
        );

        if (!cancelled && res && res.status !== "no_sub") {
          const newCache = { ...dataPages };
          res.pages.forEach((p) => {
            newCache[p.page] = { ...res, pages: [p] };
          });
          setDataPages(newCache);
          setData({
            ...res,
            current_page: pageRef.current,
            pages: [res.pages.find((p) => p.page === pageRef.current)],
          });
        }
      }

      // --- Этап 2: таблица по символу ---
      else if (stage === 2 && symbolData) {
        const symbol = symbolData.symbol;
        const currentPage = symbolPageRef.current;
        let res;

        if (mode === "dex") {
          res = await fetchDexPage(symbol, itemsPerPage, filter.current, entryPositive.current);
        } else if (mode === "futures") {
          res = await fetchFuturesPage(symbol, itemsPerPage, filter.current, entryPositive.current);
        } else {
          res = await fetchSpotPage(symbol, itemsPerPage, filter.current, entryPositive.current);
        }

        if (!cancelled && res && res.status !== "no_sub") {
          const newCache = { ...symbolPagesCache };
          res.pages.forEach((p) => {
            newCache[`${symbol}-${p.page}`] = { ...res, pages: [p] };
          });
          setSymbolPagesCache(newCache);
          setSymbolData({
            ...res,
            current_page: currentPage,
            pages: [res.pages.find((p) => p.page === currentPage)],
          });
        }
      }
    } catch (err) {
      console.error("Ошибка обновления данных при фильтре:", err);
    } finally {
      if (!cancelled) setTransitionLoading(false);
    }
  };

  refreshWithFilters();
  return () => (cancelled = true);
}, [filterState, entryPositiveState]);


  // --- Обработчик клика на кнопку из 2-го этапа (stage 2 → stage 3) ---
  const handleIdClick = async (idString) => {
    setTransitionLoading(true);
    setIdLoading(true);

    try {
      if (mode === "dex") {
        // DEX: id is "dexid_MARKET_SYMBOL"
        const parts = idString.split("_");
        const market = parts[1];
        const symbol = parts.slice(2).join("_");
        const res = await fetchDexId(symbol, market);
        setIdData({ ...res, id_string: idString });
      } else {
        const parts = idString.split("_");
        const market1 = parts[1];
        const market2 = parts[2];
        const symbol = parts[3];
        let res;
        if (mode === "futures") {
          res = await fetchFuturesId(symbol, market1, market2);
        } else {
          res = await fetchSpotId(symbol, market1, market2);
        }
        setIdData({ ...res, id_string: idString });
      }
      setStage(3);
    } catch (err) {
      console.error("Ошибка загрузки idData:", err);
    } finally {
      setTransitionLoading(false);
      setIdLoading(false);
    }
  };
  // --- Кнопка назад с 3-го этапа ---
  const handleIdBack = () => {
    setIdData(null);
    // If we came from search, go back to search results (stage 1 with search)
    if (searchQuery && searchResults) {
      setStage(1);
    } else {
      setStage(2);
    }
  };

  // --- обновление главной таблицы (1 этап) ---
  const fetchDataUpdate = async (currentPage = pageRef.current, items = itemsPerPage) => {
    try {
      const res = await fetchAllDedupe(getModeKey(), currentPage, items, filter.current, entryPositive.current);

      dataStatusRef.current = res.status || "loading";

      if (res.status !== 'no_sub')
      {

      
      const newCache = { ...dataPages };
      res.pages.forEach(p => {
        newCache[p.page] = { ...res, pages: [p] };
      });
      setDataPages(newCache);
      // 🔑 если обновили именно текущую страницу — заменим data
      if (data && data.current_page === currentPage) {
        setData({
          ...res,
          current_page: currentPage,
          pages: [res.pages.find(p => p.page === currentPage)],
        });
      }

        // 🔔 сразу инициализируем bellData
    // --- формируем данные для колокольчика ---
        let itemsFutures = [];
        let itemsSpot = [];
        let itemsDex = [];

        if (mode === "futures") {
          itemsFutures = [res.pages.find(p => p.page === currentPage)][0]?.items ?? [];
          if (spotEnabled) {
            const resSpot = await fetchAllDedupe("spot", 1, itemsPerPage, filter.current, entryPositive.current);
            itemsSpot = (resSpot && Array.isArray(resSpot.pages)) ? resSpot.pages.flatMap(p => p.items) : [];
          }
          if (dexEnabled) {
            const resDex = await fetchAllDedupe("dex", 1, itemsPerPage);
            itemsDex = (resDex && Array.isArray(resDex.pages)) ? resDex.pages.flatMap(p => p.items) : [];
          }
        } else if (mode === "spot_futures") {
          itemsSpot = [res.pages.find(p => p.page === currentPage)][0]?.items ?? [];
          if (futuresEnabled) {
            const resFutures = await fetchAllDedupe("futures", 1, itemsPerPage, filter.current, entryPositive.current);
            itemsFutures = (resFutures && Array.isArray(resFutures.pages)) ? resFutures.pages.flatMap(p => p.items) : [];
          }
          if (dexEnabled) {
            const resDex = await fetchAllDedupe("dex", 1, itemsPerPage);
            itemsDex = (resDex && Array.isArray(resDex.pages)) ? resDex.pages.flatMap(p => p.items) : [];
          }
        } else if (mode === "dex") {
          itemsDex = [res.pages.find(p => p.page === currentPage)][0]?.items ?? [];
          if (futuresEnabled) {
            const resFutures = await fetchAllDedupe("futures", 1, itemsPerPage, filter.current, entryPositive.current);
            itemsFutures = (resFutures && Array.isArray(resFutures.pages)) ? resFutures.pages.flatMap(p => p.items) : [];
          }
          if (spotEnabled) {
            const resSpot = await fetchAllDedupe("spot", 1, itemsPerPage, filter.current, entryPositive.current);
            itemsSpot = (resSpot && Array.isArray(resSpot.pages)) ? resSpot.pages.flatMap(p => p.items) : [];
          }
        }
        setBellData({ itemsFutures, itemsSpot, itemsDex });
        }
    } catch (err) {
      console.error("Ошибка обновления данных:", err);
    }
  };

  // --- обновление данных по символу (2 этап) ---
  const fetchSymbolUpdate = async (symbol, items = itemsPerPage, currentPage = symbolPageRef.current) => {
    try {
      let res;
      if (mode === "dex") {
        res = await fetchDexPage(symbol, items, filter.current, entryPositive.current);
      } else if (mode === "futures") {
        res = await fetchFuturesPage(symbol, items, filter.current, entryPositive.current);
      } else {
        res = await fetchSpotPage(symbol, items, filter.current, entryPositive.current);
      }

      const newCache = { ...symbolPagesCache };
      res.pages.forEach(p => {
        newCache[`${symbol}-${p.page}`] = { ...res, pages: [p] };
      });
      setSymbolPagesCache(newCache);

      // 🔑 если обновили именно текущую страницу — заменим symbolData
      if (symbolData && symbolData.current_page === currentPage && symbolData.symbol === symbol) {
        setSymbolData({
          ...res,
          current_page: currentPage,
          pages: [res.pages.find(p => p.page === currentPage)],
        });
      }
    } catch (err) {
      console.error("Ошибка обновления связок:", err);
    }
  };

  useEffect(() => {
  if (autoUpdate && idData) {
    const idInterval = setInterval(async () => {
      try {
        setIdLoading(true);
        const idString = idData.id_string;
        if (!idString) return;

        let res;
        if (mode === "dex") {
          const parts = idString.split("_");
          const market = parts[1];
          const symbol = parts.slice(2).join("_");
          res = await fetchDexId(symbol, market);
        } else {
          const parts = idString.split("_");
          const market1 = parts[1];
          const market2 = parts[2];
          const symbol = parts[3];
          if (mode === "futures") {
            res = await fetchFuturesId(symbol, market1, market2);
          } else {
            res = await fetchSpotId(symbol, market1, market2);
          }
        }
        // Check for token errors — if token expired, stop auto-update
        if (res && (res.detail || res.code === "token_not_valid")) {
          console.warn("Token expired — stopping auto-update");
          clearInterval(idInterval);
          return;
        }
        setIdData({ ...res, id_string: idString });
      } catch (err) {
        // If 401/403, token likely expired — stop auto-update
        if (err?.response?.status === 401 || err?.response?.status === 403) {
          console.warn("Auth error — stopping auto-update");
          clearInterval(idInterval);
          return;
        }
        console.error("Ошибка автообновления спреда:", err);
      } finally {
        setIdLoading(false);
      }
    }, 2000);

    return () => clearInterval(idInterval);
  }
}, [autoUpdate, idData, mode]);


const fetchData = async (page = 1, items = itemsPerPage) => {
  
  // Сначала проверяем кэш
  if (dataPages[page]) {
    setData({ ...dataPages[page], current_page: page });
    return dataPages[page];
  }

  try {
    const res = await fetchAllDedupe(getModeKey(), page, items, filter.current, entryPositive.current);


    // 🔹 Проверяем, есть ли вообще ответ и поле pages
    if (!res || res.status === "no_sub") {
      console.warn("❌ Подписка не активна");
      setData({ status: "no_sub" });
      return { status: "no_sub" };
    }

    if (res.status === "empty" || !Array.isArray(res.pages) || res.pages.length === 0) {
      console.warn("⚠️ Нет данных");
      setData({ status: "empty" });
      return { status: "empty" };
    }

    const newCache = { ...dataPages };
    res.pages.forEach(p => {
      newCache[p.page] = { ...res, pages: [p] };
    });
    setDataPages(newCache);

    const pageData = { 
      ...res, 
      current_page: page, 
      pages: [res.pages.find(p => p.page === page)] 
    };
    setData(pageData);

    return pageData;
  } catch (err) {
    console.error("Ошибка загрузки данных:", err);
    throw err;
  }
};

const fetchSymbolData = async (symbol, items = itemsPerPage, page = 1) => {
  const cacheKey = `${symbol}-${page}`;
  if (symbolPagesCache[cacheKey]) {
    setSymbolData({ ...symbolPagesCache[cacheKey], current_page: page });
    return;
  }

  try {
    let res;
    if (mode === "dex") {
      res = await fetchDexPage(symbol, items, filter.current, entryPositive.current);
    } else if (mode === "futures") {
      res = await fetchFuturesPage(symbol, items, filter.current, entryPositive.current);
    } else {
      res = await fetchSpotPage(symbol, items, filter.current, entryPositive.current);
    }

    const newCache = { ...symbolPagesCache };
    res.pages.forEach(p => { newCache[`${symbol}-${p.page}`] = { ...res, pages: [p] }; });
    setSymbolPagesCache(newCache);
    setSymbolData({ ...res, current_page: page, pages: [res.pages.find(p => p.page === page)] });
  } catch (err) {
    console.error("Ошибка загрузки связок:", err);
  }
};


  // Загружаем данные для 1 этапа (главная таблица)
  // useEffect(() => {
  //   if (!symbolData) {
  //     fetchData(page, itemsPerPage);
  //   }
  // }, [mode, filter, entryPositive, page, itemsPerPage]);

  // Загружаем данные для 2 этапа (по символу)
  useEffect(() => {
    if (symbolData) {
      fetchSymbolData(symbolData.symbol, itemsPerPage, symbolPage);
    }
  }, [mode, symbolPage, itemsPerPage]);

  useEffect(() => {
    if (autoUpdate) {
      intervalRef.current = setInterval(async () => {
        if (dataStatusRef.current === 'no_sub') {
          return;
        }

        // Если мы на этапе 1 — просто обновим таблицу через fetchDataUpdate
        // fetchDataUpdate внутри себя обновляет dataPages и bellData, поэтому
        // дополнительный сбор/дозапрос bellData в этом же тике не нужен.
        if (stage === 1) {
          try {
            await fetchDataUpdate(pageRef.current, itemsPerPage);
          } catch (e) {
            console.error("Ошибка в interval fetchDataUpdate:", e);
          }
          return; // <-- ВАЖНО: завершаем тик (исключаем дубли)
        }

        // Если мы на этапе 2 (подробно по символу) — обновляем символ
        if (stage === 2 && symbolData) {
          try {
            await fetchSymbolUpdate(symbolData.symbol, itemsPerPage, symbolPageRef.current);
          } catch (e) {
            console.error("Ошибка в interval fetchSymbolUpdate:", e);
          }
          // после обновления символа можно собирать bellData ниже
        }

        // --- формируем данные для колокольчика (только для stage !== 1) ---
        let itemsFutures = [];
        let itemsSpot = [];
        let itemsDex = [];

        if (mode === "futures") {
          if (stage === 1) {
            itemsFutures = dataPages[pageRef.current]?.pages[0]?.items ?? [];
          } else {
            if (futuresEnabled) {
              const resFutures = await fetchAllDedupe("futures", 1, itemsPerPage, filter.current, entryPositive.current);
              itemsFutures = (resFutures && Array.isArray(resFutures.pages)) ? resFutures.pages.flatMap(p => p.items) : [];
            }
          }
          if (spotEnabled) {
            const resSpot = await fetchAllDedupe("spot", 1, itemsPerPage, filter.current, entryPositive.current);
            itemsSpot = (resSpot && Array.isArray(resSpot.pages)) ? resSpot.pages.flatMap(p => p.items) : [];
          }
          if (dexEnabled) {
            const resDex = await fetchAllDedupe("dex", 1, itemsPerPage);
            itemsDex = (resDex && Array.isArray(resDex.pages)) ? resDex.pages.flatMap(p => p.items) : [];
          }
        } else if (mode === "spot_futures") {
          if (stage === 1) {
            itemsSpot = dataPages[pageRef.current]?.pages[0]?.items ?? [];
          } else {
            if (spotEnabled) {
              const resSpot = await fetchAllDedupe("spot", 1, itemsPerPage, filter.current, entryPositive.current);
              itemsSpot = (resSpot && Array.isArray(resSpot.pages)) ? resSpot.pages.flatMap(p => p.items) : [];
            }
          }
          if (futuresEnabled) {
            const resFutures = await fetchAllDedupe("futures", 1, itemsPerPage, filter.current, entryPositive.current);
            itemsFutures = (resFutures && Array.isArray(resFutures.pages)) ? resFutures.pages.flatMap(p => p.items) : [];
          }
          if (dexEnabled) {
            const resDex = await fetchAllDedupe("dex", 1, itemsPerPage);
            itemsDex = (resDex && Array.isArray(resDex.pages)) ? resDex.pages.flatMap(p => p.items) : [];
          }
        } else if (mode === "dex") {
          if (stage === 1) {
            itemsDex = dataPages[pageRef.current]?.pages[0]?.items ?? [];
          } else {
            if (dexEnabled) {
              const resDex = await fetchAllDedupe("dex", 1, itemsPerPage);
              itemsDex = (resDex && Array.isArray(resDex.pages)) ? resDex.pages.flatMap(p => p.items) : [];
            }
          }
          if (futuresEnabled) {
            const resFutures = await fetchAllDedupe("futures", 1, itemsPerPage, filter.current, entryPositive.current);
            itemsFutures = (resFutures && Array.isArray(resFutures.pages)) ? resFutures.pages.flatMap(p => p.items) : [];
          }
          if (spotEnabled) {
            const resSpot = await fetchAllDedupe("spot", 1, itemsPerPage, filter.current, entryPositive.current);
            itemsSpot = (resSpot && Array.isArray(resSpot.pages)) ? resSpot.pages.flatMap(p => p.items) : [];
          }
        }

        setBellData({ itemsFutures, itemsSpot, itemsDex });
      }, 2000);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [autoUpdate, symbolData, itemsPerPage, mode, futuresEnabled, spotEnabled, dexEnabled, futuresThreshold, spotThreshold, dexThreshold]);

  // Server-side search via API — exact match only
  const searchPageRef = useRef(1);
  const [searchCurrentPage, setSearchCurrentPage] = useState(1);

  const handleSearch = async (query, isRefresh = false) => {
    if (!query || query.trim().length < 1) {
      setSearchResults(null);
      return;
    }

    if (!isRefresh) setSearchLoading(true);
    try {
      const modeKey = getModeKey();
      let res;
      if (modeKey === "futures") {
        res = await fetchFuturesPage(query.trim(), itemsPerPage, filter.current, entryPositive.current);
      } else if (modeKey === "spot") {
        res = await fetchSpotPage(query.trim(), itemsPerPage, filter.current, entryPositive.current);
      } else {
        // DEX: fetch all pages and filter locally (backend needs full symbol for dex_pages)
        res = await fetchDexAll(1, 100, filter.current, entryPositive.current);
      }

      if (res && res.status !== "no_sub" && Array.isArray(res.pages) && res.pages.length > 0) {
        const q = query.trim().toUpperCase();
        // Collect ALL matching items across all pages, then re-paginate
        const allMatchingItems = [];
        res.pages.forEach(p => {
          (p.items || []).forEach(item => {
            const id = (item[1] || "").toUpperCase();
            let symbol = "";
            if (modeKey === "dex") {
              const parts = id.split("_");
              symbol = parts[parts.length - 1].replace("USDT", "");
            } else {
              const parts = id.split("_");
              symbol = parts[parts.length - 1].replace("USDT", "");
            }
            if (symbol === q) {
              allMatchingItems.push(item);
            }
          });
        });

        if (allMatchingItems.length > 0) {
          // Re-paginate with consistent page size
          const totalPages = Math.ceil(allMatchingItems.length / itemsPerPage);
          const rePages = [];
          for (let p = 0; p < totalPages; p++) {
            rePages.push({
              page: p + 1,
              items: allMatchingItems.slice(p * itemsPerPage, (p + 1) * itemsPerPage)
            });
          }
          setSearchResults({ ...res, pages: rePages, total_pages: totalPages });
        } else {
          setSearchResults({ status: "empty", pages: [] });
        }
      } else {
        setSearchResults({ status: "empty", pages: [] });
      }
    } catch (err) {
      console.error("Search error:", err);
      setSearchResults({ status: "empty", pages: [] });
    } finally {
      if (!isRefresh) setSearchLoading(false);
    }
  };

  // Debounced search
  useEffect(() => {
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(() => {
      handleSearch(searchQuery);
    }, 400);
    return () => clearTimeout(searchTimeoutRef.current);
  }, [searchQuery, mode, itemsPerPage, filterState, entryPositiveState]);

  // Auto-refresh search results every 2 seconds while searching
  useEffect(() => {
    if (!searchQuery || searchQuery.trim().length < 1) return;
    if (!autoUpdate) return;

    const searchInterval = setInterval(() => {
      handleSearch(searchQuery, true);
    }, 2000);

    return () => clearInterval(searchInterval);
  }, [searchQuery, autoUpdate, mode, itemsPerPage, filterState, entryPositiveState]);

  // Handle search page change — just switch page, no re-fetch (data already loaded)
  const handleSearchPageChange = (newPage) => {
    if (newPage >= 1 && newPage <= (searchResults?.total_pages || 1)) {
      setSearchCurrentPage(newPage);
    }
  };

  // Clear search — properly restore to stage 1 with data
  const clearSearch = () => {
    setSearchQuery("");
    setSearchResults(null);
    setSearchCurrentPage(1);
    // Ensure data is loaded
    if (!data || !data.pages || data.pages.length === 0) {
      fetchData(page, itemsPerPage);
    }
  };

  // Render search pagination
  const renderSearchPagination = () => {
    if (!searchResults || !searchResults.total_pages || searchResults.total_pages <= 1) return null;
    const total_pages = searchResults.total_pages;
    const current_page = searchCurrentPage;
    let pages = [];

    if (current_page > 2) {
      pages.push(<button key={1} className="page-btn" onClick={() => handleSearchPageChange(1)}>1</button>);
      if (current_page > 4) pages.push(<span key="dots-start" className="dots">...</span>);
    }
    for (let i = Math.max(1, current_page - 1); i <= Math.min(total_pages, current_page + 1); i++) {
      pages.push(
        <button key={i} className={`page-btn ${i === current_page ? "active" : ""}`}
          onClick={() => handleSearchPageChange(i)}>{i}</button>
      );
    }
    if (current_page < total_pages - 1) {
      if (current_page < total_pages - 3) pages.push(<span key="dots-end" className="dots">...</span>);
      pages.push(<button key={total_pages} className="page-btn" onClick={() => handleSearchPageChange(total_pages)}>{total_pages}</button>);
    }

    return (
      <div className="spreads-pagination">
        {current_page > 1 && <button className="page-btn" onClick={() => handleSearchPageChange(current_page - 1)}>◀</button>}
        {pages}
        {current_page < total_pages && <button className="page-btn" onClick={() => handleSearchPageChange(current_page + 1)}>▶</button>}
      </div>
    );
  };

  const stripUSDT = (symbol) => symbol?.endsWith("USDT") ? symbol.slice(0, -4) : symbol;

  const handleSymbolClick = async (symbol) => {
    setTransitionLoading(true);
    if (mode === "dex") {
      // DEX: symbol is like "dexsymbol_BSC_SIRENUSDT" → extract full symbol
      const fullSymbol = symbol.replace("dexsymbol_", "");
      await fetchSymbolData(fullSymbol);
    } else {
      await fetchSymbolData(symbol);
    }
    setStage(2);
    setTransitionLoading(false);
  };

  const handlePageChange = (newPage) => {
    if (stage === 1) {
      setPage(newPage);
      fetchData(newPage, itemsPerPage); // обычный запрос
    } else if (stage === 2 && symbolData) {
      setSymbolPage(newPage);
      fetchSymbolData(symbolData.symbol, itemsPerPage, newPage);
    }
  };

  const handleBack = async () => {
  setTransitionLoading(true);
  setSymbolData(null);
  setSymbolPage(1);
  setStage(1);
  await fetchData(page, itemsPerPage);
  setTransitionLoading(false);
  };

  const toggleAutoUpdate = () => {
    setAutoUpdate(!autoUpdate);
  };

  const renderSymbolPagination = () => {
  if (!symbolData) return null;
  const { total_pages } = symbolData;
  let has_prev = false;
  let has_next = false;
  let pages = [];
  const current_page = symbolPage;
  if (current_page - 1 > 0)
  {
       has_prev = true;
  }
  if (current_page < total_pages){
     has_next = true;
  }
  
  if (current_page > 2) {
    pages.push(
      <button key={1}
       className="page-btn" 
      onClick={() => handlePageChange(1)}
      >1</button>
    );
    if (current_page > 4) {
      pages.push(<span key="dots-start" className="dots">...</span>);
    }
  }

  for (let i = Math.max(1, current_page - 1); i <= Math.min(total_pages, current_page + 1); i++) {
    pages.push(
      <button
        key={i}
        className={`page-btn ${i === current_page ? "active" : ""}`}
        onClick={() => handlePageChange(i)}
      >
        {i}
      </button>
    );
  }

  if (current_page < total_pages - 1) {
    if (current_page < total_pages - 3) {
      pages.push(<span key="dots-end" className="dots">...</span>);
    }
    pages.push(
      <button key={total_pages} 
      className="page-btn" 
      onClick={() => handlePageChange(total_pages)}
      
      >
        
        {total_pages}
      </button>
    );
  }

  return (
    <div className="spreads-pagination">
      {has_prev && (
        <button className="page-btn" onClick={() => handlePageChange(current_page - 1)}>◀</button>
      )}
      {pages}
      {has_next && (
        <button className="page-btn" onClick={() => handlePageChange(current_page + 1)}>▶</button>
      )}
    </div>
  );
};

  const renderFuturesDetails = (data) => {
  if (!data?.markets?.long || !data?.markets?.short) return null;

  return (
    <>
      <h3 className="id-title">{data.coin} {data.icon}</h3>
      <div className="id-details">
        <div className="market-cards-row">
        <div className="market-card long">
          <h4 className="market-name">
            |
            <a href={data.markets.long?.link ?? "#"} target="_blank" rel="noreferrer" className="market-link">
              {data.markets.long?.market ?? "-"}
            </a>
            | — LONG
          </h4>
          <p>Текущая: <strong>{data.markets.long?.funding_current ?? "-"}%</strong></p>
          {data.markets.long?.volume24 !== "0" && <p>Объем: <strong>{data.markets.long?.volume24 ?? "-"}$</strong></p>}
          {data.markets.long?.limit !== 0 && <p>Лимит: <strong>{data.markets.long?.limit}$</strong></p>}
          <p>Стремится: {data.markets.long?.funding_target ?? "-"}%</p>
          <p>🕓: {data.markets.long?.time ?? "-"}ч</p>
        </div>

        <div className="market-card short">
          <h4 className="market-name">
            |
            <a href={data.markets.short?.link ?? "#"} target="_blank" rel="noreferrer" className="market-link">
              {data.markets.short?.market ?? "-"}
            </a>
            | — SHORT
          </h4>
          <p>Текущая: <strong>{data.markets.short?.funding_current ?? "-"}%</strong></p>
         
          {data.markets.short?.volume24 !== "0" && <p>Объем: <strong>{data.markets.short?.volume24 ?? "-"}$</strong></p>}
          {data.markets.short?.limit !== 0 && <p>Лимит: <strong>{data.markets.short?.limit}$</strong></p>}
          <p>Стремится: {data.markets.short?.funding_target ?? "-"}%</p>
          <p>🕓: {data.markets.short?.time ?? "-"}ч</p>
        </div>
        </div>
        <div className="spread-card">
          <p>Текущий: <strong>{data.spread?.current ?? "-"}%</strong></p>
          <p>Комиссия: <strong>{data.spread?.fee ?? "-"}%</strong></p>
          <p>Спред входа: <strong>{data.spread?.entry ?? "-"}%</strong> ({data.spread?.entry_raw[0] ?? "-"} | {data.spread?.entry_raw[1] ?? "-"})</p>
          <p>Спред выхода: <strong>{data.spread?.exit ?? "-"}%</strong> ({data.spread?.exit_raw[0] ?? "-"} | {data.spread?.exit_raw[1] ?? "-"})</p>
        </div>
      </div>
    </>
  );
};

const renderSpotFuturesDetails = (data) => {
  if (!data?.market1 || !data?.market2) return null;

  return (
    <>
      <h3 className="id-title">{data.symbol} {data.top_coin}</h3>
      <div className="id-details">
        <div className="market-cards-row">
        <div className="market-card long">
          <h4 className="market-name">
            |
            <a href={data.market1?.link ?? "#"} target="_blank" rel="noreferrer" className="market-link">
              {data.market1?.name ?? "-"}
            </a>
            | — {data.market1?.side ?? "BUY"}
          </h4>
          
          {data.spread?.volume24_m1 !== "0" && <p>Объем: <strong>{data.spread?.volume24_m1 ?? "-"}$</strong></p>}
        </div>

        <div className="market-card short">
          <h4 className="market-name">
            |
            <a href={data.market2?.link ?? "#"} target="_blank" rel="noreferrer" className="market-link">
              {data.market2?.name ?? "-"}
            </a>
            | — {data.market2?.side ?? "SHORT"}
          </h4>
          <p>Текущая: <strong>{data.spread?.current ?? "-"}%</strong></p>
          {data.spread?.volume24_m2 !== "0" && <p>Объем: <strong>{data.spread.volume24_m2}$</strong></p>}
          {data.spread?.limit !== 0 && <p>Лимит: <strong>{data.spread.limit}$</strong></p>}
          {data.spread?.tendency !== null && <p>Стремится: {data.spread.tendency}%</p>}
          <p>🕓: {data.spread?.time_h ?? "-"}ч</p>
        </div>
        </div>
        <div className="spread-card">
          
          <p>Текущий: <strong>{data.spread?.current ?? "-"}%</strong></p>
          <p>Комиссия: <strong>{data.fees?.total ?? "-"}%</strong></p>
          <p>Спред входа: <strong>{data.entry_spread?.value ?? "-"}%</strong> ({data.entry_spread?.bid ?? "-"} | {data.entry_spread?.ask ?? "-"})</p>
          <p>Спред выхода: <strong>{data.exit_spread?.value ?? "-"}%</strong> ({data.exit_spread?.bid ?? "-"} | {data.exit_spread?.ask ?? "-"})</p>
        </div>
      </div>
    </>
  );
};
  // --- Pagination helper ---
  const renderPagination = () => {
    if (!data || !data.pages || data.pages.length === 0 || data.total_pages <= 1) return null;

    const { current_page, total_pages } = data;

    let pages = [];

    // всегда показываем первую страницу
    if (current_page > 2) {
      pages.push(
        <button key={1} 
        className="page-btn" 
        onClick={() => handlePageChange(1)}
        >1</button>
      );
      if (current_page > 4) {
        pages.push(<span key="dots-start" className="dots">...</span>);
      }
    }

    // показываем диапазон вокруг текущей
    for (let i = Math.max(1, current_page - 1); i <= Math.min(total_pages, current_page + 1); i++) {
      pages.push(
        <button
          key={i}
          className={`page-btn ${i === current_page ? "active" : ""}`}
          onClick={() => handlePageChange(i)}
        >
          {i}
        </button>
      );
    }

    // всегда показываем последнюю страницу
    if (current_page < total_pages - 1) {
      if (current_page < total_pages - 3) {
        pages.push(<span key="dots-end" className="dots">...</span>);
      }
      pages.push(
        <button key={total_pages} 
        className="page-btn"
         onClick={() => handlePageChange(total_pages)}
         >
          {total_pages}
        </button>
      );
    }

    return (
      <div className="spreads-pagination">
        {current_page > 1 && (
          <button className="page-btn" onClick={() => handlePageChange(current_page -1)}>◀</button>
        )}
        {pages}
        {current_page < total_pages && (
          <button className="page-btn" onClick={() => handlePageChange(current_page + 1)}>▶</button>
        )}
      </div>
    );
  };

  // DEX detail view (stage 3) — matches Telegram bot format
  const renderDexDetails = (data) => {
    if (!data?.data) return null;
    const d = data.data;
    const fmtAmount = (v) => {
      if (v == null || v === 0) return "-";
      if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M$`;
      if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K$`;
      return `${v.toFixed(0)}$`;
    };
    const fmtPrice = (v) => {
      if (v == null || v === 0) return "-";
      if (v < 0.0001) return v.toExponential(2);
      if (v < 1) return `$${v.toFixed(6)}`;
      return `$${v.toFixed(2)}`;
    };
    // Get exchange link for CEX market — strip chain prefix (e.g. "BSC_SIRENUSDT" → "SIRENUSDT")
    const getCexUrl = (market, symbol) => {
      if (!market || !symbol) return null;
      // Strip chain prefix: BSC_, ETH_, ARB_, etc. (3 letters + underscore)
      const rawSymbol = symbol.toUpperCase();
      const cleanSymbol = rawSymbol.replace(/^[A-Z]{2,4}_/, "");
      const fullSymbol = cleanSymbol.endsWith("USDT") ? cleanSymbol : cleanSymbol + "USDT";
      const urls = {
        Bybit: `https://www.bybit.com/trade/usdt/${fullSymbol}`,
        Mexc: `https://futures.mexc.com/ru-RU/exchange/${fullSymbol.replace("USDT", "_USDT")}?type=linear_swap`,
        Kucoin: `https://www.kucoin.com/ru/futures/trade/${fullSymbol.replace("USDT", "USDTM")}`,
        Gateio: `https://www.gate.io/ru/futures/USDT/${fullSymbol.replace("USDT", "_USDT")}`,
        Bitget: `https://www.bitget.com/ru/futures/usdt/${fullSymbol}`,
        Huobi: `https://www.htx.com/futures/linear_swap/exchange#contract_code=${fullSymbol.replace("USDT", "-USDT")}&contract_type=swap&type=cross`,
        Okx: `https://www.okx.com/ru/trade-swap/${fullSymbol.toLowerCase().replace("usdt", "-usdt-swap")}`,
        Binance: `https://www.binance.com/ru/futures/${fullSymbol}`,
        BingX: `https://swap.bingx.com/ru-ru/${fullSymbol.replace("USDT", "-USDT")}`,
        BitMart: `https://derivatives.bitmart.com/ru-RU?symbol=${fullSymbol}&theme=dark`,
        Ourbit: `https://futures.ourbit.com/ru-RU/exchange/${fullSymbol.replace("USDT", "_USDT")}?type=linear_swap`,
        Hyperliquid: `https://app.hyperliquid.xyz/trade/${fullSymbol.replace("USDT", "")}`,
        LBank: `https://www.lbank.com/futures/${fullSymbol.toLowerCase()}`,
        Aster: `https://www.asterdex.com/ru/trade/pro/futures/${fullSymbol}`,
        XT: `https://www.xt.com/ru/futures/trade/${fullSymbol.toLowerCase().replace("usdt", "_usdt")}`,
        WEEX: `https://www.weex.com/futures/${fullSymbol.replace("USDT", "-USDT")}`,
        Phemex: `https://phemex.com/futures/${fullSymbol.replace("USDT", "-USDT")}`,
        CoinEx: `https://www.coinex.com/ru/futures/${fullSymbol.replace("USDT", "-USDT").toLowerCase()}`,
      };
      return urls[market] || null;
    };
    const cexUrl = getCexUrl(d.market, d.symbol);
    return (
      <div className="id-details">
        <h3 className="id-title">{d.displayName || d.symbol}</h3>
        <div className="market-cards-row">
          {/* DEX side — like Telegram bot "DEX — BUY" */}
          <div className="market-card long">
            <h4 className="market-name">
              |
              <a href={d.url || d.dexLink || "#"} target="_blank" rel="noreferrer" className="market-link">
                DEX
              </a>
              | — BUY
            </h4>
            {d.volume24 > 0 && <p>{t("spreads.volume24", "Объем")}: <strong>{fmtAmount(d.volume24)}</strong></p>}
            <p>{t("spreads.price", "Цена")}: <strong>{fmtPrice(d.priceUsd)}</strong></p>
          </div>

          {/* CEX side — like Telegram bot "Okx — SHORT" */}
          <div className="market-card short">
            <h4 className="market-name">
              |
              {cexUrl ? (
                <a href={cexUrl} target="_blank" rel="noreferrer" className="market-link">{d.market}</a>
              ) : d.market}
              | — SHORT
            </h4>
            <p>{t("spreads.current", "Текущая")}: <strong>{d.fundingRate != null ? `${d.fundingRate.toFixed(2)}%` : "-"}</strong></p>
            {d.volume24Cex > 0 && <p>{t("spreads.volume24", "Объем")}: <strong>{fmtAmount(d.volume24Cex)}</strong></p>}
            <p>{t("spreads.price", "Цена")}: <strong>{fmtPrice(d.cexAsk)}</strong></p>
          </div>
        </div>

        {/* Spread info — like Telegram bot */}
        <div className="spread-card">
          <p>{t("spreads.spreadEntry", "Спред входа")}: <strong>{d.diff != null ? `${d.diff.toFixed(2)}%` : "-"}</strong></p>
          {d.contract && <p>{t("spreads.contract", "Контракт")}: <strong style={{fontSize: '11px', wordBreak: 'break-all'}}>{d.contract}</strong></p>}
          {d.chain && <p>Chain: <strong>{d.chain}</strong></p>}
          {(d.url || d.dexLink) && <p>{t("spreads.dexLink", "Ссылка")}: <a href={d.url || d.dexLink} target="_blank" rel="noreferrer" style={{color: '#1994bd'}}>dexscreener</a></p>}
        </div>
      </div>
    );
  };

  return (
    <div className="spreads-container">
      {/* --- Фильтры --- */}
      <div className="filter-bar">
        <div className="spreads-search">
          <input
            type="text"
            className="spreads-search-input"
            placeholder={t("spreads.searchPlaceholder", "Поиск монеты...")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="spreads-search-clear" onClick={() => { setSearchQuery(""); setSearchResults(null); }}>×</button>
          )}
          {searchLoading && <span className="spreads-search-spinner"></span>}
        </div>
        <div className="filter-group">
          <button
            className={`filter-btn ${filter.current === "spread" ? "active" : ""}`}
            onClick={() => handleFilterChange("spread")}
          >
            {t("spreads.entry")}
          </button>
          <button
            className={`filter-btn ${filter.current === "funding" ? "active" : ""}`}
            onClick={() => handleFilterChange("funding")}
          >
            {t("spreads.funding")}
          </button>
        </div>
        <button
          className={`auto-btn ${autoUpdate ? "active" : ""}`}
          onClick={toggleAutoUpdate}
        >
          🔄 {t("spreads.auto")}
        </button>
        <div className="items-selector">
          {[5, 7, 10, 20].map((num) => (
            <button
              key={num}
              className={`items-btn ${itemsPerPage === num ? "active" : ""}`}
              onClick={() => setItemsPerPage(num)}
            >
              {num}
            </button>
          ))}
        </div>
        <button
          className={`entry-btn ${entryPositive.current ? "active" : ""}`}
          onClick={handleEntryPositiveToggle}
        >
          {t("spreads.entryGt0")}
        </button>
        <SpreadAlertBell
          mode={mode}
          futuresEnabled={futuresEnabled}
          setFuturesEnabled={setFuturesEnabled}
          spotEnabled={spotEnabled}
          setSpotEnabled={setSpotEnabled}
          dexEnabled={dexEnabled}
          setDexEnabled={setDexEnabled}
          futuresThreshold={futuresThreshold}
          setFuturesThreshold={setFuturesThreshold}
          spotThreshold={spotThreshold}
          setSpotThreshold={setSpotThreshold}
          dexThreshold={dexThreshold}
          setDexThreshold={setDexThreshold}
          blacklistAlert={blacklistAlert}
          setBlacklistAlert={setBlacklistAlert}
          itemsFutures={bellData.itemsFutures}
          itemsSpot={bellData.itemsSpot}
          itemsDex={bellData.itemsDex}
        />
      </div>

      {/* --- Контент --- */}
      <div className="spreads-content">
        {transitionLoading && <div className="spreads-loader"></div>}

        
        {/* --- Этап 3 --- */}
        {!transitionLoading && stage === 3 && idData && (
          <>
            <div className="id-header">
              <button className="spreads-back" onClick={handleIdBack}>{t("spreads.back")}</button>

              {idData.status === "ok" && idData.data && (
                <Link
                  to={
                    mode === "dex"
                      ? `/trade/futures/Dex/${idData.data.market ?? "Bitget"}/${(idData.data.symbol ?? "BSC_BTC").replace("USDT", "")}/`
                      : mode === "futures"
                        ? `/trade/futures/${idData.data.markets?.long?.market ?? "Ourbit"}/${idData.data.markets?.short?.market ?? "Mexc"}/${stripUSDT(idData.data.coin ?? "RHEA")}`
                        : `/trade/spot/${idData.data.market1?.name ?? "Bybit"}/${idData.data.market2?.name ?? "Mexc"}/${stripUSDT(idData.data.symbol ?? "BTC")}`
                  }
                  className="trade-btn"
                >
                  {t("spreads.trade")}
                </Link>
              )}
            </div>

            {idData.status === "ok" && idData.data ? (
              <>
                {mode === "futures" && renderFuturesDetails(idData.data)}
                {mode === "spot_futures" && renderSpotFuturesDetails(idData.data)}
                {mode === "dex" && renderDexDetails(idData)}
              </>
            ) : (
              <div className="no-data-message">
                {idData.status === "empty" && <p>{t("spreads.noDataForPair")}</p>}
                {idData.status === "no_sub" && <p>{t("spreads.noSubActive")}</p>}
                {!["empty", "no_sub"].includes(idData.status) && <p>{t("spreads.dataUnavailable")}</p>}
              </div>
            )}
          </>
        )}


        
        {/* --- Этап 2 --- */}
        {!transitionLoading && stage === 2 && symbolData && (() => {
          return (
            <>
              <button className="spreads-back" onClick={handleBack}>{t("spreads.back")}</button>
              <h3>{symbolData.displayName || symbolData.symbol}</h3>
              {symbolData?.pages[0]?.items.map((item, idx) => (
                <button
                  key={idx}
                  className="spread-card"
                  onClick={() => handleIdClick(item[1])} // отправка id на сервер
                >
                  <span>{item[0]}</span>
                </button>
              ))}
              {renderSymbolPagination()}
            </>
          );
        })()}

        {/* --- Этап 1 --- */}
        {!transitionLoading && stage === 1 && (() => {
          // Show search results if search is active — behave like stage 2
          if (searchQuery && searchQuery.trim().length >= 1) {
            if (searchLoading) {
              return <div className="no-data-message"><p>{t("spreads.searching", "Поиск...")}</p></div>;
            }
            if (searchResults && searchResults.status === "empty") {
              return (
                <div className="no-data-message">
                  <p>{t("spreads.coinNotFound", "Монета не найдена")}: "{searchQuery}"</p>
                  <button className="spreads-back" onClick={clearSearch}>{t("spreads.backToList", "← Назад к списку")}</button>
                </div>
              );
            }
            if (searchResults && Array.isArray(searchResults.pages) && searchResults.pages.length > 0) {
              const pageIdx = Math.min(searchCurrentPage - 1, searchResults.pages.length - 1);
              const searchPageItems = searchResults.pages[pageIdx]?.items || [];
              const isDexSearch = mode === "dex";
              return (
                <>
                  <button className="spreads-back" onClick={clearSearch}>⬅ {t("spreads.backToList", "Back to list")}</button>
                  <h3 style={{textAlign: 'center', marginBottom: '10px'}}>{searchQuery.toUpperCase()}USDT</h3>
                  {searchPageItems.map((item, idx) => (
                    <button
                      key={idx}
                      className="spread-card"
                      onClick={() => {
                        if (isDexSearch) {
                          // DEX search results from fetchDexAll have IDs like "dexsymbol_BSC_SIRENUSDT"
                          // Extract full symbol (chain_symbol) for stage 2
                          const id = item[1] || "";
                          let fullSymbol;
                          if (id.startsWith("dexsymbol_")) {
                            fullSymbol = id.replace("dexsymbol_", "");
                          } else {
                            // Fallback: idParts = ["dexid", "MARKET", "CHAIN", "SYMBOLUSDT"]
                            const idParts = id.split("_");
                            const chain = idParts[2] || "";
                            const symbolPart = idParts[3] || "";
                            fullSymbol = `${chain}_${symbolPart}`;
                          }
                          handleSymbolClick("dexsymbol_" + fullSymbol);
                        } else {
                          handleIdClick(item[1]);
                        }
                      }}
                    >
                      <span>{item[0]}</span>
                    </button>
                  ))}
                  {searchResults.total_pages > 1 && renderSearchPagination()}
                </>
              );
            }
          }

          const currentPageData = dataPages[page];

          if (!currentPageData || !currentPageData.pages?.[0]?.items?.length) {
            return <div className="no-data-message">
              {dataStatusRef.current === "empty" && <p>{t("spreads.noData")}</p>}
              {dataStatusRef.current === "no_sub" && <div className="error-center-container">
                          <div className="error-subscription-container">
                              <img src="/images/info.svg" alt="Info" className="error-subscription-icon" />
                              <div className="error-subscription-text">
                                  <h3 className="error-subscription-title">{t("spreads.noSub")}</h3>
                                  <p className="error-subscription-description">
                                      {t("spreads.noSubDesc")}
                                  </p>
                                  <Link to={'/subscription'} className="sub-button">{t("spreads.subscription")}</Link>
                              </div>
                          </div>
                          </div>}
              {!["empty","no_sub", "loading"].includes(dataStatusRef.current) && <p>{t("spreads.dataUnavailable")}</p>}
            </div>;
          }

          return currentPageData.pages[0]?.items.map((item, idx) => (
            <button
              key={idx}
              className="spread-card clickable"
              onClick={() => handleSymbolClick(item[1])}
            >
              <span>{item[0]}</span>
            </button>
          ));
        })()}
      </div>

      {/* --- Пагинация (hide during search) --- */}
      {!transitionLoading && stage === 1 && data && !searchQuery && renderPagination()}

      {/* --- Переключатель режимов внизу --- */}
      <div className="mode-switch-bottom">
        <button
          className={`mode-btn ${mode === "futures" ? "active" : ""}`}
          onClick={() => setMode("futures")}
        >
          Futures
        </button>
        <button
          className={`mode-btn ${mode === "spot_futures" ? "active" : ""}`}
          onClick={() => setMode("spot_futures")}
        >
          Spot+Futures
        </button>
        <button
          className={`mode-btn ${mode === "dex" ? "active" : ""}`}
          onClick={() => setMode("dex")}
        >
          DEX
        </button>
      </div>
    </div>
  );
}

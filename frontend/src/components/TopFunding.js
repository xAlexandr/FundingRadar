import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { fetchTopFunding, fetchTopFundingSpot } from "../api/api.js";
import "./TopFunding.css";

// Futures URL builder — matches Go service createMessageToFutures links
const getFuturesUrl = (market, symbol) => {
  if (!symbol) return "#";
  const cleanSymbol = symbol.replace("USDT", "").toUpperCase();
  const fullSymbol = cleanSymbol + "USDT";
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
    CoinEx: `https://www.coinex.com/ru/futures/${fullSymbol.replace("USDT", "-USDT").toLowerCase()}`,
    Ourbit: `https://futures.ourbit.com/ru-RU/exchange/${fullSymbol.replace("USDT", "_USDT")}?type=linear_swap`,
    Hyperliquid: `https://app.hyperliquid.xyz/trade/${cleanSymbol}`,
    LBank: `https://www.lbank.com/futures/${cleanSymbol.toLowerCase()}`,
    Aster: `https://www.asterdex.com/ru/trade/pro/futures/${fullSymbol}`,
    XT: `https://www.xt.com/ru/futures/trade/${fullSymbol.toLowerCase().replace("usdt", "_usdt")}`,
    WEEX: `https://www.weex.com/futures/${fullSymbol.replace("USDT", "-USDT")}`,
    Phemex: `https://phemex.com/futures/${fullSymbol.replace("USDT", "-USDT")}`,
  };
  return urls[market] || "#";
};

// Spot URL builder — for spot/futures mode, market1 is spot
const getSpotUrl = (market, symbol) => {
  if (!symbol) return "#";
  const cleanSymbol = symbol.replace("USDT", "").toUpperCase();
  const fullSymbol = cleanSymbol + "USDT";
  const urls = {
    Bybit: `https://www.bybit.com/ru-RU/trade/spot/${fullSymbol.replace("USDT", "/USDT")}`,
    Mexc: `https://www.mexc.com/ru-RU/exchange/${fullSymbol.replace("USDT", "_USDT")}?_from=search_spot_trade`,
    Kucoin: `https://www.kucoin.com/ru/trade/${fullSymbol.replace("USDT", "-USDT")}`,
    Gateio: `https://www.gate.io/ru/trade/${fullSymbol.replace("USDT", "_USDT")}`,
    Bitget: `https://www.bitget.com/ru/spot/${fullSymbol}`,
    Huobi: `https://www.htx.com/trade/${fullSymbol.toLowerCase().replace("usdt", "_usdt")}?type=spot`,
    Okx: `https://www.okx.com/ru/trade-spot/${fullSymbol.toLowerCase().replace("usdt", "-usdt")}`,
    Binance: `https://www.binance.com/ru/trade/${fullSymbol.replace("USDT", "_USDT")}`,
    BingX: `https://bingx.com/ru-ru/spot/${fullSymbol}/`,
    BitMart: `https://www.bitmart.com/trade/ru-RU?symbol=${fullSymbol.replace("USDT", "_USDT")}`,
    CoinEx: `https://www.coinex.com/ru/exchange/${fullSymbol.replace("USDT", "-USDT").toLowerCase()}`,
    Ourbit: `https://www.ourbit.com/ru-RU/exchange/${fullSymbol.replace("USDT", "_USDT")}?_from=search_spot_trade`,
    Hyperliquid: `https://app.hyperliquid.xyz/trade/${cleanSymbol}`,
    LBank: `https://www.lbank.com/trade/${fullSymbol.toLowerCase().replace("usdt", "_usdt")}`,
    Aster: `https://www.asterdex.com/ru/trade/pro/spot/${fullSymbol}`,
    XT: `https://www.xt.com/ru/trade/${fullSymbol.toLowerCase().replace("usdt", "_usdt")}`,
    WEEX: `https://www.weex.com/spot/${fullSymbol.replace("USDT", "-USDT")}`,
    Phemex: `https://phemex.com/trade/${fullSymbol.replace("USDT", "-USDT")}`,
  };
  return urls[market] || "#";
};

const formatFunding = (val) => {
  if (val == null) return "0.00%";
  // val from API is already a percentage (e.g. 0.05 means 0.05%)
  const v = Number(val);
  if (isNaN(v)) return "0.00%";
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
};

const TopFunding = ({ embedded = false }) => {
  const { t } = useTranslation();
  const [futuresCoins, setFuturesCoins] = useState([]);
  const [spotCoins, setSpotCoins] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const [resFutures, resSpot] = await Promise.all([
          fetchTopFunding(),
          fetchTopFundingSpot()
        ]);
        if (mounted) {
          if (resFutures && resFutures.status === "ok" && Array.isArray(resFutures.coins)) {
            setFuturesCoins(resFutures.coins);
          }
          if (resSpot && resSpot.status === "ok" && Array.isArray(resSpot.coins)) {
            setSpotCoins(resSpot.coins);
          }
          setLastUpdate(new Date());
        }
      } catch (e) {
        console.error("TopFunding load error", e);
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    const interval = setInterval(load, 10000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  const renderCoinCard = (coin, idx, isSpot = false) => {
    const diffClass = coin.spread < 0 ? "negative" : "";
    // market1 URL: spot links for spot/futures, futures links for futures
    const market1Url = isSpot ? getSpotUrl(coin.market1, coin.symbol) : getFuturesUrl(coin.market1, coin.symbol);
    // market2 URL: always futures links
    const market2Url = getFuturesUrl(coin.market2, coin.symbol);
    return (
      <div className="top-funding-card" key={idx}>
        <div className="top-funding-rank">#{idx + 1}</div>
        <div className="top-funding-coin">
          <span className="top-funding-symbol">{coin.symbol?.replace("USDT", "")}</span>
          <span className="top-funding-pair">/USDT</span>
        </div>
        <div className="top-funding-exchanges">
          <a
            href={market1Url}
            target="_blank"
            rel="noopener noreferrer"
            className="top-funding-exchange"
          >
            <span className="top-funding-market-name">{coin.market1}</span>
            <span className={`top-funding-funding ${coin.funding1 < 0 ? "negative" : ""}`}>{formatFunding(isSpot ? null : coin.funding1)}</span>
          </a>
          <span className="top-funding-vs">vs</span>
          <a
            href={market2Url}
            target="_blank"
            rel="noopener noreferrer"
            className="top-funding-exchange"
          >
            <span className="top-funding-market-name">{coin.market2}</span>
            <span className={`top-funding-funding ${coin.funding2 < 0 ? "negative" : ""}`}>{formatFunding(isSpot ? coin.funding2 : coin.funding2)}</span>
          </a>
        </div>
        <div className={`top-funding-diff ${diffClass}`}>
          {t("topFunding.fundingDiff", "Разница")}: <strong>{formatFunding(coin.spread)}</strong>
        </div>
      </div>
    );
  };

  if (loading && futuresCoins.length === 0 && spotCoins.length === 0) {
    return (
      <section className={`top-funding-section ${embedded ? "embedded" : ""}`}>
        <div className="container">
          <h2>{t("topFunding.title", "Топ-16 монет по фандингу")}</h2>
          <p className="top-funding-sub">{t("topFunding.subtitle", "Актуальные ставки финансирования между биржами")}</p>
          <div className="top-funding-loading">Загрузка...</div>
        </div>
      </section>
    );
  }

  return (
    <section className={`top-funding-section ${embedded ? "embedded" : ""}`}>
      <div className="container">
        <h2>{t("topFunding.title", "Топ-16 монет по фандингу")}</h2>
        <p className="top-funding-sub">{t("topFunding.subtitle", "Актуальные ставки финансирования между биржами")}</p>
        <p className="top-funding-info">{t("topFunding.info", "Обновляется каждые 10 секунд. Значения фандинга — актуальные ставки за период.")}</p>
        {lastUpdate && (
          <p className="top-funding-updated">
            {t("topFunding.lastUpdate", "Последнее обновление")}: {lastUpdate.toLocaleTimeString()}
          </p>
        )}

        {/* Futures section */}
        {futuresCoins.length > 0 && (
          <>
            <h3 className="top-funding-section-title">{t("topFunding.futuresTitle", "Фьючерсы")}</h3>
            <div className="top-funding-grid">
              {futuresCoins.map((coin, idx) => renderCoinCard(coin, idx, false))}
            </div>
          </>
        )}

        {/* Spot/Futures section */}
        {spotCoins.length > 0 && (
          <>
            <h3 className="top-funding-section-title">{t("topFunding.spotTitle", "Спот/Фьючерсы")}</h3>
            <div className="top-funding-grid">
              {spotCoins.map((coin, idx) => renderCoinCard(coin, idx, true))}
            </div>
          </>
        )}
      </div>
    </section>
  );
};

export default TopFunding;

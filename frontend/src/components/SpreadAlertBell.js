import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { fetchFuturesAll, fetchSpotAll } from "../api/api";
import "./SpreadAlertBell.css";

export default function SpreadAlertBell({
  mode,
  futuresEnabled,
  setFuturesEnabled,
  spotEnabled,
  setSpotEnabled,
  dexEnabled,
  setDexEnabled,
  futuresThreshold,
  setFuturesThreshold,
  spotThreshold,
  setSpotThreshold,
  dexThreshold,
  setDexThreshold,
  blacklistAlert,
  setBlacklistAlert,
  itemsFutures,
  itemsSpot,
  itemsDex,
}) {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);

  // используем ref, чтобы не было задержки из-за стейта
  const lastFuturesSoundRef = React.useRef(0);
  const lastSpotSoundRef = React.useRef(0);
  const lastDexSoundRef = React.useRef(0);

  const playAlert = () => {
    const audio = new Audio("/sound/alert.mp3");
    audio.play();
  };

 
  const [inputValue, setInputValue] = useState("");

  const [alertActive, setAlertActive] = useState(false);

 

  const stripUSDT = (symbol) =>
    symbol?.endsWith("USDT") ? symbol.slice(0, -4) : symbol;

  // 🔎 Быстрая проверка (каждые 150мс)
  useEffect(() => {
    const fastCheck = setInterval(() => {
      const now = Date.now();
      let futuresTriggered = false;
      let spotTriggered = false;
      let dexTriggered = false;

      if (futuresEnabled && futuresThreshold && itemsFutures?.length) {
        itemsFutures.forEach(([label, symbol]) => {
          const coin = stripUSDT(symbol);
          if (!blacklistAlert.includes(coin)) {
            const value = parseFloat(label.split(":")[1]);
            if (!isNaN(value) && value >= parseFloat(futuresThreshold)) {
              futuresTriggered = true;
            }
          }
        });
      }

      if (spotEnabled && spotThreshold && itemsSpot?.length) {
        itemsSpot.forEach(([label, symbol]) => {
          const coin = stripUSDT(symbol);
          if (!blacklistAlert.includes(coin)) {
            const value = parseFloat(label.split(":")[1]);
            if (!isNaN(value) && value >= parseFloat(spotThreshold)) {
              spotTriggered = true;
            }
          }
        });
      }

      if (dexEnabled && dexThreshold && itemsDex?.length) {
        itemsDex.forEach(([label, id]) => {
          // DEX IDs: "dexsymbol_BSC_SIRENUSDT" → extract "SIREN"
          let coin;
          if (id && id.startsWith("dexsymbol_")) {
            const parts = id.split("_");
            // parts = ["dexsymbol", "BSC", "SIRENUSDT"]
            coin = (parts[parts.length - 1] || "").replace("USDT", "");
          } else {
            coin = stripUSDT(id);
          }
          if (!blacklistAlert.includes(coin)) {
            const value = parseFloat(label.split(":")[1]);
            if (!isNaN(value) && value >= parseFloat(dexThreshold)) {
              dexTriggered = true;
            }
          }
        });
      }

      // --- FUTURES ---
      if (futuresTriggered) {
        if (now - lastFuturesSoundRef.current >= 2000) {
          playAlert();
          lastFuturesSoundRef.current = now;
        }
      }

      // --- SPOT ---
      if (spotTriggered) {
        if (now - lastSpotSoundRef.current >= 2000) {
          playAlert();
          lastSpotSoundRef.current = now;
        }
      }

      // --- DEX ---
      if (dexTriggered) {
        if (now - lastDexSoundRef.current >= 2000) {
          playAlert();
          lastDexSoundRef.current = now;
        }
      }

      // общий "активный" статус для подсветки иконки
      if (futuresEnabled || spotEnabled || dexEnabled) {
        setAlertActive(true);
      } else {
        setAlertActive(false);
      }
    }, 150);

    return () => clearInterval(fastCheck);
  }, [
    futuresEnabled,
    spotEnabled,
    dexEnabled,
    futuresThreshold,
    spotThreshold,
    dexThreshold,
    blacklistAlert,
    itemsFutures,
    itemsSpot,
    itemsDex,
  ]);


  const addToBlacklist = () => {
    if (!inputValue) return;
    const newCoins = inputValue
      .split(",")
      .map(c => c.trim().toUpperCase())
      .filter(c => c.length > 0);

    setBlacklistAlert(prev => Array.from(new Set([...prev, ...newCoins])));
    setInputValue("");
  };

  const removeFromBlacklist = () => {
    if (!inputValue) return;
    const toRemove = inputValue
      .split(",")
      .map(c => c.trim().toUpperCase());

    setBlacklistAlert(prev => prev.filter(c => !toRemove.includes(c)));
    setInputValue("");
  };

  return (
    <div className="spreads-alert-bell-wrapper">
      <button
        className={`spreads-alert-bell ${alertActive ? "active" : ""}`}
        onClick={() => setIsOpen(true)}
      >
        🔔
      </button>

      {isOpen && (
        <div className="spreads-modal-overlay" onClick={() => setIsOpen(false)}>
          <div className="spreads-modal-content" onClick={(e) => e.stopPropagation()}>
            <button
              className="spreads-close-modal-button"
              onClick={() => setIsOpen(false)}
            >
              ✕
            </button>

            <div className="spreads-alert-input-block">
              <label>{t("bell.futuresThreshold", "Порог для фьючерсов (%)")}</label>
              <div className="spreads-input-with-toggle">
                <input
                  type="number"
                  value={futuresThreshold}
                  onChange={(e) => setFuturesThreshold(e.target.value)}
                  placeholder={t("bell.thresholdPlaceholder", "Напр. 5")}
                />
                <button
                  className={`spreads-circle-toggle ${futuresEnabled ? "on" : "off"}`}
                  onClick={() => setFuturesEnabled(!futuresEnabled)}
                >
                  <span></span>
                </button>
              </div>

              <label>{t("bell.spotThreshold", "Порог для спот/фьючерсов (%)")}</label>
              <div className="spreads-input-with-toggle">
                <input
                  type="number"
                  value={spotThreshold}
                  onChange={(e) => setSpotThreshold(e.target.value)}
                  placeholder={t("bell.thresholdPlaceholder10", "Напр. 10")}
                />
                <button
                  className={`spreads-circle-toggle ${spotEnabled ? "on" : "off"}`}
                  onClick={() => setSpotEnabled(!spotEnabled)}
                >
                  <span></span>
                </button>
              </div>

              <label>{t("bell.dexThreshold", "Порог для DEX (%)")}</label>
              <div className="spreads-input-with-toggle">
                <input
                  type="number"
                  value={dexThreshold}
                  onChange={(e) => setDexThreshold(e.target.value)}
                  placeholder={t("bell.thresholdPlaceholder5", "Напр. 5")}
                />
                <button
                  className={`spreads-circle-toggle ${dexEnabled ? "on" : "off"}`}
                  onClick={() => setDexEnabled(!dexEnabled)}
                >
                  <span></span>
                </button>
              </div>

              <label>{t("bell.blacklist", "Чёрный список")}</label>
              <div className="spreads-blacklist-input-row">
                <input
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder="BTC, ETH, DOGE"
                />
                <button className="spreads-alert-button" onClick={addToBlacklist}>+</button>
                <button className="spreads-alert-button" onClick={removeFromBlacklist}>−</button>
              </div>
            </div>

            {blacklistAlert.length > 0 && (
              <div className="spreads-blacklist-box">
                {blacklistAlert.join(", ")}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

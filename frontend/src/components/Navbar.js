import React from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import "./Navbar.css";

const Navbar = () => {
    const location = useLocation();
    const { t } = useTranslation();
    const lastTrade = JSON.parse(localStorage.getItem("lastTrade")) || {};
    const defaultPath = `/trade/${lastTrade.spOrFt || "futures"}/${lastTrade.market1 || "Bybit"}/${lastTrade.market2 || "Mexc"}/${lastTrade.coin || "BTC"}/`;

    return (
        <nav className="navbar">
            <Link to={defaultPath} className={location.pathname.startsWith("/trade") ? "active" : ""}>
                <div className="nav-item">
                    <img src="/images/graph.svg" alt="Trade" className="nav-icon" />
                    <span>{t("navbar.trade", "Торговля")}</span>
                </div>
            </Link>
            <Link to="/spreads" className={location.pathname === "/spreads" ? "active" : ""}>
                <div className="nav-item">
                    <img src="/images/trade.svg" alt="Spreads" className="nav-icon" />
                    <span>{t("navbar.spreads", "Спреды")}</span>
                </div>
            </Link>
            <Link to="/subscription" className={location.pathname === "/subscription" ? "active" : ""}>
                <div className="nav-item">
                    <img src="/images/wallet.svg" alt="Subscription" className="nav-icon" />
                    <span>{t("navbar.subscription", "Подписка")}</span>
                </div>
            </Link>
            <Link to="/info" className={location.pathname === "/info" ? "active" : ""}>
                <div className="nav-item">
                    <img src="/images/info.svg" alt="Info" className="nav-icon info-icon" />
                    <span>{t("navbar.info", "Информация")}</span>
                </div>
            </Link>
        </nav>
    );
};

export default Navbar;

// src/components/Sidebar.jsx
import React, { useState, useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import navConfig from "../navConfig";
import tarifsIcon from "../assets/icons/tarifs.svg";
import infoIcon from "../assets/icons/info.svg";
import faqIcon from "../assets/icons/faq.svg";
import marketsIcon from "../assets/icons/markets.svg";

const tradingIcon = process.env.PUBLIC_URL + "/images/trading.svg";

const Icon = ({ name, className = "" }) => {
  const props = { className: `mainnav-icon ${className}`, width: 18, height: 18, viewBox: "0 0 24 24" };
  const icons = { tarifs: tarifsIcon, info: infoIcon, faq: faqIcon, markets: marketsIcon, trading: tradingIcon };
  switch (name) {
    case "home":
      return (<svg {...props} fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 11.5L12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1V11.5z"/></svg>);
    case "tarifs":
      return <img src={icons[name]} alt={name} className="mainnav-icon" />;
    case "info":
      return <img src={icons[name]} alt={name} className="mainnav-icon" />;
    case "markets":
      return <img src={icons[name]} alt={name} className="mainnav-icon" />;
    case "trading":
      return <img src={tradingIcon} alt={name} className="mainnav-icon" />;
    case "faq":
      return <img src={icons[name]} alt={name} className="mainnav-icon" />;
    default:
      return (<svg {...props}><circle cx="12" cy="12" r="8" /></svg>);
  }
};

const Sidebar = ({ isOpen = false, onClose = () => {} }) => {
  const { t, i18n } = useTranslation();
  const [openKeys, setOpenKeys] = useState({});
  const loc = useLocation();

  useEffect(() => {
    navConfig.forEach(item => {
      if (item.children && item.children.some(c => loc.pathname.startsWith(c.to))) {
        setOpenKeys(prev => ({ ...prev, [item.key]: true }));
      }
    });
  }, [loc.pathname]);

  const toggleSection = (key) => setOpenKeys(prev => ({ ...prev, [key]: !prev[key] }));
  const changeLanguage = (lng) => {
    i18n.changeLanguage(lng);
    localStorage.setItem("lang", lng);
  };

  return (
    <>
      <aside className={`mainnav-sidebar ${isOpen ? "open" : ""}`} aria-hidden={!isOpen && window.innerWidth <= 980}>
        <div className="mainnav-logo-container">
          <img
            src="/images/NoFonFR.svg"   // <-- путь к твоему SVG-файлу
            alt="Logo"
            className="mainnav-logo-img"
          />
        </div>

        <nav className="mainnav-nav" role="navigation">
          {navConfig.map(item => (
            <div key={item.key} className="mainnav-item-wrap">
              {!item.children ? (
                <NavLink
                  to={item.to}
                  onClick={onClose}
                  className={({ isActive }) => `mainnav-link ${isActive ? "mainnav-link--active" : ""}`}
                >
                  <div className="mainnav-link-left">
                    <Icon name={item.icon} />
                    <span className="mainnav-link-text">{t(item.i18nKey)}</span>
                  </div>
                </NavLink>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => toggleSection(item.key)}
                    className={`mainnav-link mainnav-link--toggle ${openKeys[item.key] ? "open" : ""}`}
                  >
                    <div className="mainnav-link-left">
                      <Icon name={item.icon} />
                      <span className="mainnav-link-text">{t(item.i18nKey)}</span>
                    </div>
                    <svg className="mainnav-chevron" width="16" height="16" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round"/></svg>
                  </button>

                  <div className={`mainnav-submenu ${openKeys[item.key] ? "open" : ""}`}>
                    {item.children.map(child => (
                      <NavLink
                        key={child.key}
                        to={child.to}
                        onClick={onClose}
                        className={({ isActive }) => `mainnav-sublink ${isActive ? "mainnav-sublink--active" : ""}`}
                      >
                        {t(child.i18nKey)}
                      </NavLink>
                    ))}
                  </div>
                </>
              )}
            </div>
          ))}
        </nav>

        {/* RU/EN и версия — в самом низу */}
        <div className="mainnav-bottom">
          <div className="mainnav-lang">
            <button className={`mainnav-lang-btn ${i18n.language === "ru" ? "active" : ""}`} onClick={() => changeLanguage("ru")}>RU</button>
            <button className={`mainnav-lang-btn ${i18n.language === "en" ? "active" : ""}`} onClick={() => changeLanguage("en")}>EN</button>
          </div>
          <div className="mainnav-copy">v6.9</div>
        </div>
      </aside>

      <div className={`mainnav-overlay ${isOpen ? "visible" : ""}`} onClick={onClose} />
    </>
  );
};

export default Sidebar;

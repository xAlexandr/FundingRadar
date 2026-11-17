// src/components/LayoutWeb.jsx
import React, { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Sidebar from "./Sidebar";
import { useTranslation } from "react-i18next";

const LayoutWeb = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  const { t, i18n } = useTranslation();
  const lang = i18n.language;

  const rootClass = `mainnav-layout no-bottom-navbar ${location.pathname === "/" ? "has-hero-banner" : ""}`;

  return (
    <div className={rootClass}>
      {/* header: справа будет бургер */}
      <header className="mainnav-header">
        <div className="mainnav-header-inner">
          <div className="mainnav-header-left">
            {/* по желанию тут логотип/название, если нужно */}
          </div>

          {/* бургер — только в шапке, справа */}
          <button
            className={`mainnav-burger ${sidebarOpen ? "is-open" : ""}`}
            onClick={() => setSidebarOpen(s => !s)}
            aria-label="Toggle sidebar"
            aria-expanded={sidebarOpen}
          >
            <span className="mainnav-burger-line" />
            <span className="mainnav-burger-line" />
            <span className="mainnav-burger-line" />
          </button>
        </div>
      </header>

      {/* Sidebar получает isOpen и onClose */}
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <main className="mainnav-content">
        {/* баннер только на главной */}
        {location.pathname === "/" && (
          <div className="landing-banner-wrapper" aria-hidden={false}>
            {/* сам баннер (не трогаем порядок, сохраняем дизайн и фон) */}
            <div className="landing-mainnav-hero-image" aria-hidden="true">
              <img src="/images/banner.png" alt="Hero banner" />
            </div>

            {/* overlay поверх баннера */}
            <div className="banner-overlay-content" role="region" aria-label={t('banner.ariaLabel') || 'Banner actions'}>
              <div className="banner-left">
                <h1 className="banner-title">{t('banner.title')}</h1>
                <p className="banner-subtitle">{t('banner.subtitle')}</p>
              </div>

              <div className="banner-right" aria-hidden={false}>
                <a href="https://t.me/funding_cryptoprojects_bot" target="_blank" className="banner-btn banner-btn--buy" aria-label={t('banner.buy')}>
                  {t('banner.buy')}
                </a>

                <a href="https://t.me/xWHOxAMxIx" target="_blank" className="banner-btn banner-btn--consult" aria-label={t('banner.consult')}>
                  {/* иконка + текст: текст будет скрыт на маленьких экранах, иконка останется */}
                  <svg className="consult-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false" width="18" height="18">
              
                    <path d="M4 4h16v10H7l-3 3V4z" fill="currentColor"/>
                  </svg>
                  <span className="consult-text">{t('banner.consult')}</span>
                </a>
              </div>
            </div>
          </div>
        )}

        <Outlet />
      </main>
    </div>
  );
};

export default LayoutWeb;

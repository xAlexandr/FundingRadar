import React, { useEffect, useRef, useState } from "react";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { FaYoutube, FaTelegramPlane } from "react-icons/fa";
import "./Pricing.css";


const Pricing = () => {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;

  const telegramUrl = t("trial.telegramUrl", "https://t.me/fundingradar_official");
  const fundingBotUrl = t("trial.fundingBotUrl", "https://t.me/funding_cryptoprojects_bot");
  const supportUrl = t("trial.supportUrl", "https://t.me/xWHOxAMxIx");


  const urls = {
    telegram: t("social.telegramUrl", "https://t.me/fundingradar_official"),
    support: t("social.supportUrl", "https://t.me/xWHOxAMxIx"),
    youtube: t("social.youtubeUrl", "https://www.youtube.com/@fundingradar"),
    privateChat: t("social.privateChatUrl", "https://t.me/+iIBEKxXveOMwYjRi"),
  };


  return (
    <main className="landing">
      <Helmet>
        <html lang={lang} />
        <title>{t("seo.pricing_title")}</title>
        <meta name="description" content={t("seo.pricing_desc")} />
        <link rel="canonical" href={`https://fundingradar.ru/tarifs`} />
      </Helmet>

     {/* PRICING */}
      <section className="landing-pricing nopad">
        <div className="container">
          <h2>{t("pricing.title")}</h2>

          <div className="pricing-grid">
            {/* Тариф 1 месяц */}
            <div className="pricing-card">
              <h3>{t("pricing.month1.title")}</h3>
              <div className="landing-price">
                <span className="old-price">{t("pricing.month1.oldPrice")}</span>
                <span className="new-price">{t("pricing.month1.newPrice")}</span>
              </div>
              <ul className="tariff-features">
                <li>{t("pricing.month1.features.0")}</li>
                <li>{t("pricing.month1.features.1")}</li>
                <li>{t("pricing.month1.features.2")}</li>
                <li>{t("pricing.month1.features.3")}</li>
                <li>{t("pricing.month1.features.4")}</li>
                <li>{t("pricing.month1.features.5")}</li>
                <li>{t("pricing.month1.features.6")}</li>
                <li><strong>{t("pricing.month1.features.7")}</strong></li>
                <li><em>{t("pricing.month1.features.8")}</em></li>
              </ul>
              <a href={fundingBotUrl} target="_blank"  className="btn-primary">{t("pricing.tryBtn")}</a>
            </div>

            {/* Тариф 3 месяца */}
            <div className="pricing-card popular">
              <div className="badge">{t("pricing.month3.badge")}</div>
              <h3>{t("pricing.month3.title")}</h3>
              <div className="landing-price">
                <span className="old-price">{t("pricing.month3.oldPrice")}</span>
                <span className="new-price">{t("pricing.month3.newPrice")}</span>
                <span className="discount">{t("pricing.month3.discount")}</span>
              </div>
              <ul className="tariff-features">
                <li>{t("pricing.month3.features.0")}</li>
                <li>{t("pricing.month3.features.1")}</li>
                <li>{t("pricing.month3.features.2")}</li>
                <li>{t("pricing.month3.features.3")}</li>
                <li>{t("pricing.month3.features.4")}</li>
                <li>{t("pricing.month3.features.5")}</li>
                <li>{t("pricing.month3.features.6")}</li>
                <li><strong>{t("pricing.month3.features.7")}</strong></li>
                <li><em>{t("pricing.month3.features.8")}</em></li>
              </ul>
              <a href={fundingBotUrl} target="_blank" className="btn-primary">{t("pricing.tryBtn")}</a>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
};

export default Pricing;

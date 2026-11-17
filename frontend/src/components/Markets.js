import React from "react";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import "./Markets.css";

const Markets = () => {
  const { t, i18n } = useTranslation();
  const lang = i18n.language || "ru";

  // Получаем объект items из i18n (возвращаем объект)
  const itemsObj = t("markets.items", { returnObjects: true }) || {};
  const itemsKeys = Object.keys(itemsObj);

  return (
    <main className="markets-page">
      <Helmet>
        <html lang={lang} />
        <title>{t("seo.markets_title")}</title>
        <meta name="description" content={t("markets.subtitle")} />
        <link rel="canonical" href="https://fundingradar.ru/markets" />
      </Helmet>

      <section className="markets-section">
        <h1 className="markets-title">{t("markets.title")}</h1>
        <p className="markets-subtitle">{t("markets.subtitle")}</p>

        <div className="markets-table-wrap">
          <table className="markets-table" role="table" aria-label={t("markets.title")}>
            <thead>
              <tr>
                <th className="col-name">{t("markets.columns.name")}</th>
                <th className="col-taker">{t("markets.columns.taker")}</th>
                <th className="col-maker">{t("markets.columns.maker")}</th>
                <th className="col-active">{t("markets.columns.activeSince")}</th>
              </tr>
            </thead>

            <tbody>
              {itemsKeys.map((key) => {
                const m = itemsObj[key] || {};
                const logo = m.logo || "";
                const name = m.name || key;
                return (
                  <tr className="markets-row" key={key}>
                    <td className="markets-col markets-col-name">
                      <div className="markets-name-cell">
                        {logo ? (
                          <img src={logo} alt={`${name} logo`} className="markets-logo" />
                        ) : (
                          <div className="markets-logo-fallback">{(name || "").slice(0,2).toUpperCase()}</div>
                        )}
                        <span className="markets-name-text">{name}</span>
                      </div>
                    </td>

                    <td className="markets-col markets-col-taker">{m.taker ?? "-"}</td>
                    <td className="markets-col markets-col-maker">{m.maker ?? "-"}</td>
                    <td className="markets-col markets-col-active">{m.activeSince ?? "-"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
};

export default Markets;

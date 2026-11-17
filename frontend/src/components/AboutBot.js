import React from "react";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import "./FundingIs.css";

const Section = ({ title, title2, text, list, list2, img, img2, img3, caption, caption2, caption3, imgWidth, imgWidth2, imgWidth3, text2, text3, text4, text5, textlow, textlow2, textlow3, textlow4, textlow5, textlow6, textlow7, textlow8, textlow9 }) => (
  <section className="funding-section">
    {title && <h2 className="funding-section-title">{title}</h2>}

    {img && (
      <figure className="funding-image-block">
        <img src={img} alt={caption || title || "image"} style={{ maxWidth: imgWidth || "700px" }} className="funding-image" />
        {caption && <figcaption className="funding-caption">{caption}</figcaption>}
      </figure>
    )}

    {text && (
      <p className="funding-text">
        {text}
      </p>
    )}

    {img2 && (
      <figure className="funding-image-block">
        <img src={img2} alt={caption2 || title || "image"} style={{ maxWidth: imgWidth2 || "700px" }} className="funding-image" />
        {caption2 && <figcaption className="funding-caption">{caption2}</figcaption>}
      </figure>
    )}

    {text2 && (
      <p className="funding-text">
        {text2}
      </p>
    )}

    {text3 && (
      <p className="funding-text">
        {text3}
      </p>
    )}

    {text4 && (
      <p className="funding-text">
        {text4}
      </p>
    )}

    {text5 && (
      <p className="funding-text">
        {text5}
      </p>
    )}

    {list && Array.isArray(list) && list.length > 0 && (
      <ul className="funding-list">
        {list.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    )}

    {title2 && <h2 className="funding-section-title">{title2}</h2>}

    {textlow && (
      <p className="funding-text">
        {textlow}
      </p>
    )}

    {textlow2 && (
      <p className="funding-text">
        {textlow2}
      </p>
    )}

    {img3 && (
      <figure className="funding-image-block">
        <img src={img3} alt={caption3 || title || "image"} style={{ maxWidth: imgWidth3 || "700px" }} className="funding-image" />
        {caption3 && <figcaption className="funding-caption">{caption3}</figcaption>}
      </figure>
    )}

     {textlow3 && (
      <p className="funding-text">
        {textlow3}
      </p>
    )}

    {textlow4 && (
      <p className="funding-text">
        {textlow4}
      </p>
    )}

    {list2 && Array.isArray(list2) && list2.length > 0 && (
      <ul className="funding-list">
        {list2.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    )}

    {textlow5 && (
      <p className="funding-text">
        {textlow5}
      </p>
    )}

    {textlow6 && (
      <p className="funding-text">
        {textlow6}
      </p>
    )}

    {textlow7 && (
      <p className="funding-text">
        {textlow7}
      </p>
    )}

    {textlow8 && (
      <p className="funding-text">
        {textlow8}
      </p>
    )}

    {textlow9 && (
      <p className="funding-text">
        {textlow9}
      </p>
    )}
  </section>
);

const AboutBot = () => {
  const { t, i18n } = useTranslation();
  const lang = i18n.language || "ru";

  const botUrl = t("fundingIs.bot_url") || "https://t.me/funding_cryptoprojects_bot";
  const botImage = t("fundingIs.bot_image");
  const channelUrl = t("aboutBot.subtitle");

  return (
    <main className="landing fundingis-page">
      <Helmet>
        <html lang={lang} />
        <title>{t("aboutBot.title")}</title>
        <meta name="description" content={t("aboutBot.paragraph1")} />
        <link rel="canonical" href="https://fundingradar.ru/information/instruction" />
      </Helmet>

      <section className="fundingis-wrap">
        <header className="fundingis-header">
          <h1 className="fundingis-title">{t("aboutBot.title")}</h1>
          <a
            href={channelUrl}
            target="_blank"
            rel="noreferrer"
            className="fundingis-subtitle"
          >
            {channelUrl}
          </a>
        </header>

        <article className="fundingis-article">
          {/* Введение */}
          <Section
            title={t("aboutBot.intro")}
            text={t("aboutBot.paragraph1")}
          />

          {/* Основные разделы бота */}
          <Section
            title={t("aboutBot.section1.title")}
            list={t("aboutBot.section1.list", { returnObjects: true })}
            img={t("aboutBot.section1.img")}
            caption={t("aboutBot.section1.caption")}
            imgWidth="300px"
          />

          {/* Терминология и показатели */}
          <Section
            title={t("aboutBot.section2.title")}
            text={t("aboutBot.section2.text")}
            list={t("aboutBot.section2.list", { returnObjects: true })}
            img={t("aboutBot.section2.img")}
            caption={t("aboutBot.section2.caption")}
            imgWidth="300px"
          />

          {/* Спред */}
          <Section
            title={t("aboutBot.section3.title")}
            text={t("aboutBot.section3.text")}
            list={t("aboutBot.section3.list", { returnObjects: true })}
            img={t("aboutBot.section3.img")}
            caption={t("aboutBot.section3.caption")}
            imgWidth="300px"
          />

          {/* График */}
          <Section
            title={t("aboutBot.section4.title")}
            text={t("aboutBot.section4.paragraph")}
            img={t("aboutBot.section4.img")}
            caption={t("aboutBot.section4.caption")}
            imgWidth="300px"
          />

          {/* Вкладка торговля */}
          <Section
            title={t("aboutBot.section5.title")}
            text={t("aboutBot.section5.text2")}
            list={t("aboutBot.section5.list", { returnObjects: true })}
            img={t("aboutBot.section5.img")}
            caption={t("aboutBot.section5.caption")}
            imgWidth="300px"
            img3={t("aboutBot.section5.img3")}
            caption3={t("aboutBot.section5.caption3")}
            imgWidth3="300px"
            list2={t("aboutBot.section5.list2", { returnObjects: true })}
            
          />

          {/* Вкладка спреды */}
          <Section
            title={t("aboutBot.section9.title")}
            list={t("aboutBot.section9.list", { returnObjects: true })}
            img={t("aboutBot.section9.img")}
            caption={t("aboutBot.section9.caption")}
            imgWidth="300px"
            img3={t("aboutBot.section9.img3")}
            caption3={t("aboutBot.section9.caption3")}
            imgWidth3="300px"
            list2={t("aboutBot.section9.list2", { returnObjects: true })}
            
          />


          {/* На вкладке Подписка */}
          <Section
            title={t("aboutBot.section6.title")}
            list={t("aboutBot.section6.list", { returnObjects: true })}
            img={t("aboutBot.section6.img")}
            caption={t("aboutBot.section6.caption")}
            imgWidth="300px"
          />

          {/* На вкладке с Информацией */}
          <Section
            title={t("aboutBot.section7.title")}
            text={t("aboutBot.section7.paragraph")}
            img={t("aboutBot.section7.img")}
            caption={t("aboutBot.section7.caption")}
            imgWidth="300px"
          />

          {/* Рекомендации */}
          <Section
            title={t("aboutBot.section8.title")}
            text={t("aboutBot.section8.paragraph")}
          />

          {/* Финальный текст */}
          <Section
            textlow={t("aboutBot.textfuter")}
          />

          <div className="fundingis-links">
            <a
              href={t("fundingIs.subtitle")}
              target="_blank"
              rel="noreferrer"
              className="fundingis-link"
            >
              {t("fundingIs.telegram")}
            </a>

            <a href={botUrl} target="_blank" rel="noreferrer" className="fundingis-bot">
              {botImage && (
                <img src={botImage} alt="Bot" className="fundingis-bot-img" />
              )}
              <span>{t("fundingIs.bot")}</span>
            </a>
          </div>
        </article>
      </section>
    </main>
  );
};

export default AboutBot;

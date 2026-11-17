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

    {list && list.length > 0 && (
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

    {list2 && list2.length > 0 && (
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

const FundingIs = () => {
  const { t, i18n } = useTranslation();
  const lang = i18n.language || "ru";

  const botUrl = t("fundingIs.bot_url") || "https://t.me/funding_cryptoprojects_bot";
  const botImage = t("fundingIs.bot_image"); // если есть картинка для кнопки
  const channelUrl = t("fundingIs.subtitle");

  return (
    <main className="landing fundingis-page">
      <Helmet>
        <html lang={lang} />
        <title>{t("fundingIs.title")}</title>
        <meta name="description" content={t("fundingIs.paragraph1")} />
        <link rel="canonical" href="https://fundingradar.ru/information/funding" />
      </Helmet>

      <section className="fundingis-wrap">
        <header className="fundingis-header">
          <h1 className="fundingis-title">{t("fundingIs.title")}</h1>
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
          <Section 
          title={t("fundingIs.intro")} 
          text={t("fundingIs.paragraph1")}
          text2={t("fundingIs.paragraph2")} 
          text3={t("fundingIs.paragraph3")}
          text4={t("fundingIs.paragraph4")}
          text5={t("fundingIs.paragraph5")}
          />

          <Section
            title={t("fundingIs.howItWorks")}
            list={t("fundingIs.steps", { returnObjects: true })}
          />

          <Section
            title={t("fundingIs.exampleTitle")}
            list={t("fundingIs.exampleSteps", { returnObjects: true })}
          />

          <Section
            title={t("fundingIs.whyWorks")}
            list={t("fundingIs.whyPoints", { returnObjects: true })}
          />

          <Section
            title={t("fundingIs.sectionPractice")}
            text={t("fundingIs.sectionPracticeText")}
            img2={t("fundingIs.sectionPracticeImg")}
            caption2={t("fundingIs.sectionPracticeCaption")}
            imgWidth2="350px"
          />


          <Section
            title={t("fundingIs.sectionFundingRate")}
            text={t("fundingIs.sectionFundingRateText")}
          />

          <Section
            title={t("fundingIs.fundingTime")}
            text={t("fundingIs.fundingTimeText")}
            img={t("fundingIs.fundingTimeImg")}
            caption={t("fundingIs.fundingTimeCaption")}
            imgWidth="700px"
            title2={t("fundingIs.payoutTitle")}
            textlow={t("fundingIs.payoutText")}
            img3={t("fundingIs.payoutImg")}
            textlow3={t("fundingIs.payoutNote")}
            caption3={t("fundingIs.payoutCaption")}
            imgWidth3="700px"
            textlow4={t("fundingIs.typesFunding")}
            list2={t("fundingIs.fundingTypes", { returnObjects: true })}
            textlow5={t("fundingIs.fundingTypesNote")}
          />

          <Section
            title={t("fundingIs.hedgeTitle")}
            text={t("fundingIs.hedgeText")}
            text2={t("fundingIs.hedgeText2")}
            text3={t("fundingIs.hedgeText3")}
          />

          <Section
            title={t("fundingIs.arbitrageTypes")}
            text={t("fundingIs.arbitrageText")}
            list={t("fundingIs.arbitrageList", { returnObjects: true })}
            textlow={t("fundingIs.arbitrageText2")}
            img3={t("fundingIs.arbitrageImg3")}
            caption3={t("fundingIs.arbitrageCaption3")}
            textlow3={t("fundingIs.arbitrageText3")}
            textlow4={t("fundingIs.arbitrageText4")}
            textlow5={t("fundingIs.arbitrageText5")}
          />


            <Section
            title={t("fundingIs.priceDifferenceTitle")}
            text={t("fundingIs.priceDifferenceText")}
            
            list={t("fundingIs.priceDifferenceList2", { returnObjects: true })}
            textlow={t("fundingIs.priceDifferenceNote")}
            text2={t("fundingIs.priceDifferenceExampleText2")}
            textlow2={t("fundingIs.priceDifferenceNote2")}
            textlow4={t("fundingIs.botConceptsText")}
            list2={t("fundingIs.botConceptsList", { returnObjects: true })}
          />

            <Section
            title={t("fundingIs.priceArbitrageStrategyTitle")}
            text={t("fundingIs.priceArbitrageStrategyText")}
            text2={t("fundingIs.priceArbitrageStrategyText2")}
            text3={t("fundingIs.priceArbitrageStrategyText3")}

          />

            <Section
            title={t("fundingIs.fundingArbitrageStrategyTitle")}
            text={t("fundingIs.fundingArbitrageStrategyText")}
            text2={t("fundingIs.fundingArbitrageStrategyText2")}
            img3={t("fundingIs.fundingArbitrageStrategyImg3")}
            caption3={t("fundingIs.fundingArbitrageStrategyCaption3")}
            imgWidth3="300px"
            textlow3={t("fundingIs.exampleBundleText")}
            textlow4={t("fundingIs.exampleBundleText2")}
            textlow5={t("fundingIs.exampleBundleText3")}
            textlow6={t("fundingIs.exampleBundleText4")}
            textlow7={t("fundingIs.exampleBundleText5")}
            textlow8={t("fundingIs.exampleBundleText6")}
            textlow9={t("fundingIs.exampleBundleText7")}
          />

             <Section
            title={t("fundingIs.howToEnterBundlesTitle")}
            text={t("fundingIs.howToEnterBundlesText")}
            text2={t("fundingIs.howToEnterBundlesText2")}
            img3={t("fundingIs.fundingArbitrageStrategyImg3")}
            caption3={t("fundingIs.fundingArbitrageStrategyCaption3")}
            imgWidth3="300px"
            textlow3={t("fundingIs.webVersionText")}
            textlow4={t("fundingIs.preparationText")}
            textlow5={t("fundingIs.preparationText2")}
            textlow6={t("fundingIs.preparationText3")}
            textlow7={t("fundingIs.quickSwitchText")}
          />

             <Section
            title={t("fundingIs.examplesTitle")}
            text={t("fundingIs.examplesText")}
            img2={t("fundingIs.examplesArbitrageStrategyImg2")}
            caption2={t("fundingIs.examplesArbitrageStrategyCaption2")}
            imgWidth2="300px"
            text2={t("fundingIs.hbarShortText")}
            text3={t("fundingIs.hbarLongText")}
            img3={t("fundingIs.examplesArbitrageStrategyImg3")}
            caption3={t("fundingIs.examplesArbitrageStrategyCaption3")}
            imgWidth3="300px"
            textlow3={t("fundingIs.hbarLongText2")}
            textlow4={t("fundingIs.hbarLongText3")}

          />

            <Section
            title={t("fundingIs.risksTitle")}
            text={t("fundingIs.risksText")}
            list={t("fundingIs.risksList", { returnObjects: true })}
          />
        

            <Section
            title={t("fundingIs.automationTitle")}
            text={t("fundingIs.automationText")}
            text2={t("fundingIs.automationText2")}
            list2={t("fundingIs.automationList", { returnObjects: true })}
          />


            <Section
            title={t("fundingIs.webVersionTitle")}
            text={t("fundingIs.webVersionText")}
            list2={t("fundingIs.webVersionList", { returnObjects: true })}
            textlow5={t("fundingIs.webVersionNote")}
          />

          <Section
            title={t("fundingIs.conclusion")}
            text={t("fundingIs.conclusionText")}
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

export default FundingIs;

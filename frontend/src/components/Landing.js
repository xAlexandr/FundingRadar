import React, { useEffect, useRef, useState } from "react";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { FaYoutube, FaTelegramPlane } from "react-icons/fa";
import "./Landing.css";
import Testimonials from "./Testimonials";

const slides = [
  { src: "/images/app1.png", captionKey: "landing.screens.1", alt: "FundingBot screenshot 1" },
  { src: "/images/app2.png", captionKey: "landing.screens.2", alt: "FundingBot screenshot 2" },
  { src: "/images/app3.png", captionKey: "landing.screens.3", alt: "FundingBot screenshot 3" },
  { src: "/images/app4.png", captionKey: "landing.screens.4", alt: "FundingBot screenshot 4" },
  { src: "/images/app5.png", captionKey: "landing.screens.5", alt: "FundingBot screenshot 5" },
];

// helper: preload + decode one image
const preloadAndDecode = async (url) => {
  try {
    const img = new Image();
    img.src = url;
    await new Promise((res) => {
      img.onload = res;
      img.onerror = res; // resolve even on error to avoid hang
    });
    if (img.decode) {
      await img.decode().catch(() => null);
    }
    return true;
  } catch (e) {
    return false;
  }
};

const Landing = () => {
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

  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [imagesLoaded, setImagesLoaded] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(() => slides.map(() => false));
  const timeoutRef = useRef(null);
  const AUTOPLAY = 3500;

  // preload images sequentially (more reliable for decode)
  useEffect(() => {
    let mounted = true;
    (async () => {
      for (let i = 0; i < slides.length; i++) {
        if (!mounted) break;
        const ok = await preloadAndDecode(slides[i].src);
        if (!mounted) break;
        setImgLoaded((prev) => {
          const copy = [...prev];
          copy[i] = ok;
          return copy;
        });
      }
      if (mounted) setImagesLoaded(true);
    })();

    return () => {
      mounted = false;
      clearTimeout(timeoutRef.current);
    };
  }, []);

  // autoplay
  useEffect(() => {
    if (!imagesLoaded || paused) return;
    clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      setIndex((prev) => (prev + 1) % slides.length);
    }, AUTOPLAY);
    return () => clearTimeout(timeoutRef.current);
  }, [index, paused, imagesLoaded]);

  // keyboard
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "ArrowLeft") setIndex((i) => (i - 1 + slides.length) % slides.length);
      if (e.key === "ArrowRight") setIndex((i) => (i + 1) % slides.length);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const goTo = (i) => {
    setIndex(i);
    setPaused(false);
  };


  return (
    <main className="landing">
      <Helmet>
        <html lang={lang} />
        <title>{t("seo.home_title")}</title>
        <meta name="description" content={t("seo.home_desc")} />
        <meta
          name="keywords"
          content="арбитраж фандинга, сканер фандинга, funding arbitrage, funding scanner, Hyperliquid, CEX DEX arbitrage"
        />
        <link rel="canonical" href="https://fundingradar.ru/" />
      </Helmet>

      {/* HERO */}
      <section className="landing-hero">
        <div className="container">
        <div className="landing-hero-left">
          <h1>{t("landing.title", "FundingBot — арбитраж фандинга между CEX и DEX биржами")}</h1>

          <p className="landing-hero-sub">
            {t(
              "landing.lead"
            )}
          </p>

          <ul className="landing-short-features">
            <li>{t("landing.point1", "Мгновенные сигналы — данные каждые 100 мс")}</li>
            <li>{t("landing.point2", "Поддержка Hyperliquid, Binance, Bybit и других")}</li>
            <li>{t("landing.point3")}</li>
          </ul>

          <div className="landing-buttons">
            <a href={fundingBotUrl} target="_blank" className="btn-primary">{t("landing.trial", "6 часов бесплатно")}</a>
            <a href={supportUrl} target="_blank" className="btn-outline">{t("landing.ask", "Задать вопрос")}</a>
          </div>

          <div className="landing-support">
            <h4>{t("landing.supportTitle", "Поддержка и обучение")}</h4>
            <p>
              {t(
                "landing.supportText",
                "Подробные подсказки в интерфейсе, обучающие материалы и закрытый чат для пользователей — помогаем понять и применять стратегии арбитража фандинга."
              )}
            </p>
          </div>
        </div>

        <div
          className="landing-hero-right"
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
        >
          {!imagesLoaded ? (
            <div className="slider-loading" aria-live="polite">
              {t("landing.loading", "Загрузка изображений...")}
            </div>
          ) : (
            <>
              <div
                className="slider-viewport"
                role="region"
                aria-roledescription="carousel"
                aria-label={t("landing.carouselLabel", "Скриншоты приложения")}
              >
                <div
                  className="slider-track"
                  style={{
                    transform: `translate3d(-${index * 100}%, 0, 0)`,
                    width: `${slides.length * 20}%`,
                  }}
                >
                  {slides.map((s, i) => (
                    <div
                      key={i}
                      className="slider-slide"
                      aria-hidden={i !== index}
                      aria-roledescription="slide"
                      aria-label={t(s.captionKey)}
                    >
                      <div className="slide-caption" aria-live={i === index ? "polite" : "off"}>
                        {t(s.captionKey)}
                      </div>

                      <div className="slide-image-wrap">
                        <img
                          src={s.src}
                          alt={t(s.alt, s.alt)}
                          className={`slide-image ${imgLoaded[i] ? "loaded" : ""}`}
                          onLoad={() =>
                            setImgLoaded((prev) => {
                              if (prev[i]) return prev;
                              const copy = [...prev];
                              copy[i] = true;
                              return copy;
                            })
                          }
                          decoding="async"
                          loading="eager"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div
                className="slider-dots"
                role="tablist"
                aria-label={t("landing.dotsLabel", "Переключатели слайдов")}
              >
                {slides.map((_, i) => (
                  <button
                    key={i}
                    className={`slider-dot ${i === index ? "active" : ""}`}
                    onClick={() => goTo(i)}
                    aria-label={t("landing.dotAria", { i: i + 1 })}
                    aria-pressed={i === index}
                    role="tab"
                  />
                ))}
              </div>
            </>
          )}
        </div>
        </div>
      </section>

      {/* BENEFITS */}
      <section className="landing-benefits">
        <div className="container">
        <h2>{t("landing.whyTitle", "Почему выбирают FundingBot")}</h2>

        <div className="benefits-grid">
          <div className="benefit-card">
            <div className="benefit-icon">⚡</div>
            <div className="benefit-body">
              <h3>{t("benefits.speed")}</h3>
              <p>{t("benefits.speedText")}</p>
            </div>
          </div>

          <div className="benefit-card">
            <div className="benefit-icon">💹</div>
            <div className="benefit-body">
              <h3>{t("benefits.exchanges")}</h3>
              <p>{t("benefits.exchangesText")}</p>
            </div>
          </div>

          <div className="benefit-card">
            <div className="benefit-icon">🔒</div>
            <div className="benefit-body">
              <h3>{t("benefits.safety")}</h3>
              <p>{t("benefits.safetyText")}</p>
            </div>
          </div>

          <div className="benefit-card">
            <div className="benefit-icon">🎓</div>
            <div className="benefit-body">
              <h3>{t("benefits.support")}</h3>
              <p>{t("benefits.supportText")}</p>
            </div>
          </div>
        </div>

        <div className="landing-seo-text">
          <p>{t("benefits.seoText")}</p>
        </div>
        </div>
      </section>

      {/* CTA */}
      <section className="landing-cta">
         <div className="container">
        <h2>{t("landing.ctaTitle","Попробуйте FundingBot бесплатно")}</h2>
        <p>{t("landing.ctaText","Тестовый период — 6 часов. Получите доступ ко всем функциям и начните арбитраж фандинга уже сегодня.")}</p>
        <a href={telegramUrl} target="_blank" className="btn-primary">{t("landing.tryNow","Попробовать сейчас")}</a>
        </div>
      </section>

      {/* HERO + Product */}
      <section className="landing-hero-product">
         <div className="container">
        <div className="landing-hero-left">
          <h1>{t("landingProduct.title")}</h1>
          
          <p>{t(
            "landingProduct.description"
          )}</p>

          <a href={telegramUrl} target="_blank" className="btn-outline">{t("landingProduct.button", "Подробнее о продукте")}</a>

          {/* Второй ряд под основным текстом */}
          <div className="product-subgrid">
            <div className="sub-images">
              <img src="/images/example1.jpg" alt={t("landingProduct.subImage1Alt", "Пример 1")} />
              <img src="/images/example2.jpg" alt={t("landingProduct.subImage2Alt", "Пример 2")} />
            </div>
            <div className="sub-text">
              <p>{t(
                "landingProduct.case"
              )}</p>
            </div>
          </div>
        </div>

        <div className="landing-hero-right">
          <img src="/images/main-product.jpg" className="border-img" alt={t("landingProduct.mainImageAlt", "Арбитраж Фьючерсов")} />
        </div>
        </div>
      </section>

      {/* PRICING */}
      <section className="landing-pricing">
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

      {/* TESTIMONIALS */}
      <Testimonials/>
      

      <section className="landing-trial" aria-labelledby="trial-heading">
      <div className="container trial-grid">
        <div className="trial-left">
          <h2 id="trial-heading">{t("trial.title", "Хотите проверить, как он работает?")}</h2>

          <p className="trial-lead">
            {t(
              "trial.lead",
              "Напишите в поддержку, и мы дадим вам тестовый доступ на 6 часов."
            )}
          </p>

          <p className="trial-note">
            {t(
              "trial.note",
              "Также вы можете зайти на наш Telegram-канал и посмотреть результаты наших клиентов."
            )}{" "}
            <a
              className="trial-link"
              href={telegramUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("trial.telegramText", "Открыть канал")}
            </a>
          </p>

          <div className="trial-actions">
            <a
              className="btn-primary trial-btn"
              target="_blank"
              href={supportUrl}
            >
              {t("trial.button", "6 часов бесплатно")}
            </a>
            <a
              className="btn-outline trial-outline"
              target="_blank"
              href={supportUrl}
            >
              {t("trial.contactSupport", "Написать в поддержку")}
            </a>
          </div>
        </div>

        <div className="trial-right" role="img" aria-label={t("trial.imageAlt", "Робот")}>
          {/* замените путь /images/robot.png на ваш файл */}
          <img src="/images/robot.png" alt={t("trial.imageAlt", "Иллюстрация робота")} className="trial-image" />
        </div>
      </div>
    </section>


    {/* AFFILIATE SECTION */}
    <section className="landing-affiliate">
      <div className="container affiliate-grid">
        <div className="affiliate-left">
          <img
            src="/images/affiliate.png"
            alt={t("affiliate.imageAlt")}
            className="affiliate-image"
          />
        </div>
        <div className="affiliate-right">
          <h2>{t("affiliate.title")}</h2>
          <p className="affiliate-sub">{t("affiliate.subtitle")}</p>
          <p className="affiliate-text">{t("affiliate.description")}</p>
          <a href="https://t.me/xWHOxAMxIx" target="_blank" className="btn-primary">
            {t("affiliate.button")}
          </a>
        </div>
      </div>
    </section>        


    <section className="landing-socials" aria-labelledby="socials-heading">
      <div className="container socials-grid">
        <div className="social-left">
          <h2 id="socials-heading">{t("social.title")}</h2>

          <div className="social-buttons" role="list">
            <a
              className="social-btn"
              href={urls.telegram}
              target="_blank"
              rel="noopener noreferrer"
              role="listitem"
            >
              <span className="social-icon" aria-hidden><FaTelegramPlane/></span>
              <span className="social-label">{t("social.buttons.telegram")}</span>
            </a>

            <a
              className="social-btn"
              href={urls.support}
              target="_blank"
              rel="noopener noreferrer"
              role="listitem"
            >
              <span className="social-icon" aria-hidden>💬</span>
              <span className="social-label">{t("social.buttons.support")}</span>
            </a>

            <a
              className="social-btn"
              href={urls.youtube}
              target="_blank"
              rel="noopener noreferrer"
              role="listitem"
            >
              <span className="social-icon" aria-hidden><FaYoutube/></span>
              <span className="social-label">{t("social.buttons.youtube")}</span>
            </a>

            <a
              className="social-btn"
              href={urls.privateChat}
              target="_blank"
              rel="noopener noreferrer"
              role="listitem"
            >
              <span className="social-icon" aria-hidden>🔒</span>
              <span className="social-label">{t("social.buttons.privateChat")}</span>
            </a>
          </div>

          <p className="social-sub">
            {t("social.sub", "Если у вас остались вопросы, мы с радостью на них ответим.")}
          </p>

          <p className="social-disclaimer">
            {t(
              "social.disclaimer",
              "ВАЖНО! Мы не только разработчики программного обеспечения, но и трейдеры. Поэтому наш бот разработан с максимальной надежностью и стабильностью. Мы не даем рекомендации и обещания по заработку, не советуем вам куда-то вкладывать свои деньги и ни в коем случае не работаем с вашими деньгами. Наш софт полностью ручной, все ваши деньги только под вашим личным управлением. Мы приводим примеры, как на арбитраже в прошлом заработали наши клиенты, но мы не советуем повторять действия один в один. Ваш заработок зависит исключительно от ваших действий и от факторов рынка. Команда CryptoProjects не несет ответственность за ваши результаты."
            )}
          </p>
        </div>

        <div className="social-right" aria-hidden>
          {/* замените путь на вашу картинку, например /images/social-illustration.png */}
          <img
            src="/images/social-robot.png"
            alt={t("social.imageAlt")}
            className="social-image"
            loading="lazy"
          />
        </div>
      </div>
    </section>
    </main>
  );
};

export default Landing;

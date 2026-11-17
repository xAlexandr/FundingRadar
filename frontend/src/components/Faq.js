import React, { useState } from "react";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import "./Faq.css";

/*
  Ключи переводов: faq.q1, faq.a1 и т.д.
  Локальное состояние open внутри каждой карточки — исключает взаимное влияние.
*/

const faqItems = [
  { id: "q1", q: "faq.q1", a: "faq.a1" },
  { id: "q2", q: "faq.q2", a: "faq.a2" },
  { id: "q3", q: "faq.q3", a: "faq.a3" },
  { id: "q4", q: "faq.q4", a: "faq.a4" },
  { id: "q5", q: "faq.q5", a: "faq.a5" },
  { id: "q6", q: "faq.q6", a: "faq.a6" },
  { id: "q7", q: "faq.q7", a: "faq.a7" },
  { id: "q8", q: "faq.q8", a: "faq.a8" },
  { id: "q9", q: "faq.q9", a: "faq.a9" },
];

const FaqItem = ({ item, question, answer }) => {
  // локальное состояние — карточка полностью независима
  const [open, setOpen] = useState(false);

  const headId = `faq-head-${item.id}`;
  const bodyId = `faq-body-${item.id}`;

  // защита: не открывать, если нет ответа или перевод не найден (t вернул ключ)
  const canOpen = () => {
    if (!answer || typeof answer !== "string") return false;
    const trimmed = answer.trim();
    if (!trimmed) return false;
    // если это ключ переводов (например "faq.a1") — считаем перевода нет
    if (/^faq\./.test(trimmed)) return false;
    return true;
  };

  const handleToggle = () => {
    if (!canOpen()) return;
    setOpen(prev => !prev);
  };

  return (
    <div className={`faq-card ${open ? "open" : ""}`} aria-expanded={open}>
      <button
        id={headId}
        className="faq-head"
        onClick={handleToggle}
        aria-controls={bodyId}
        aria-expanded={open}
        type="button"
      >
        <span className="faq-title">{question}</span>
        <span className={`faq-arrow ${open ? "rot" : ""}`} aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M6 9l6 6 6-6" />
          </svg>
        </span>
      </button>

      <div
        id={bodyId}
        className={`faq-body ${open ? "show" : ""}`}
        role="region"
        aria-labelledby={headId}
      >
        <div className="faq-body-inner">{answer}</div>
      </div>
    </div>
  );
};

const Faq = () => {
  const { t, i18n } = useTranslation();
  const lang = i18n.language || "ru";

  // подготовим элементы с текстами (t может вернуть ключ, это нормально)
  const rendered = faqItems.map(item => ({
    ...item,
    question: t(item.q),
    answer: t(item.a)
  }));

  // Разбиваем массив на 2 колонки так, чтобы порядок сохранился:
  const left = rendered.filter((_, idx) => idx % 2 === 0);
  const right = rendered.filter((_, idx) => idx % 2 === 1);

  return (
    <main className="landing faq-page">
      <Helmet>
        <html lang={lang} />
        <title>{t("seo.faq_title")}</title>
        <meta name="description" content={t("seo.faq_desc")} />
        <link rel="canonical" href="https://fundingradar.ru/faq" />
      </Helmet>

      <section className="faq-wrap container">
        <header className="faq-header">
          <h1>{t("faq.title")}</h1>
          <p className="faq-sub">{t("faq.subtitle")}</p>
        </header>

        {/* Новый layout: 2 независимых столбца */}
        <div className="faq-grid">
          <div className="faq-col">
            {left.map(item => (
              <FaqItem key={item.id} item={item} question={item.question} answer={item.answer} />
            ))}
          </div>

          <div className="faq-col">
            {right.map(item => (
              <FaqItem key={item.id} item={item} question={item.question} answer={item.answer} />
            ))}
          </div>
        </div>

        <div className="faq-cta">
          <p>
            {t("faq.still_need_help")}
            {" "}
            <a
              className="btn-outline"
              href={t("trial.supportUrl")}
              target="_blank"
              rel="noreferrer"
            >
              {t("faq.contact_support")}
            </a>
          </p>
        </div>
      </section>
    </main>
  );
};

export default Faq;

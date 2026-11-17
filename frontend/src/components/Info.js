import React, { useState, useEffect, useRef } from "react";
import { FaYoutube, FaTelegramPlane } from "react-icons/fa";
import { useTranslation } from "react-i18next";
import "./Info.css";

const Info = () => {
    const { t, i18n } = useTranslation();
    const [openIndex, setOpenIndex] = useState(null);
    const answerRefs = useRef({});

    const changeLanguage = (lng) => {
        i18n.changeLanguage(lng);
        localStorage.setItem("lang", lng);
    };

    useEffect(() => {
        Object.keys(answerRefs.current).forEach((key) => {
            const element = answerRefs.current[key];
            if (element) {
                if (parseInt(key) === openIndex) {
                    element.style.maxHeight = element.scrollHeight + "px";
                } else {
                    element.style.maxHeight = "0px";
                }
            }
        });
    }, [openIndex]);


    const faqItems = [
        {
            question: t("faq.q1"),
            answer: t("faq.a1")
        },
        {
            question: t("faq.q2"),
            answer: t("faq.a2")
        },
        {
            question: t("faq.q3"),
            answer: t("faq.a3")
        },
        {
            question: t("faq.q4"),
            answer: t("faq.a4")
        },
        {
            question: t("faq.q5"),
            answer: t("faq.a5")
        },
        {
            question: t("faq.q6"),
            answer: t("faq.a6")
        },
        {
            question: t("faq.q7"),
            answer: t("faq.a7")
        },
        {
            question: t("faq.q8"),
            answer: t("faq.a8")
        },
        {
            question: t("faq.q9"),
            answer: t("faq.a9")
        },
    ];

    const toggleFAQ = (index) => {
        setOpenIndex(prevIndex => (prevIndex === index ? null : index));
    };

    return (
        <div className="info-container">
            <div className="info-header-row">
                <h2>{t("infoPage.title", "Информация")}</h2>
                <div className="info-lang-switch">
                    <button className={`info-lang-btn ${i18n.language === "ru" ? "active" : ""}`} onClick={() => changeLanguage("ru")}>RU</button>
                    <button className={`info-lang-btn ${i18n.language === "en" ? "active" : ""}`} onClick={() => changeLanguage("en")}>EN</button>
                </div>
            </div>
            <p className="info-description">
                {t("infoPage.description", "На данной странице вы сможете найти всю необходимую информацию о нашем боте арбитража фандинга.")}
            </p>

            <div className="info-links">
                <a href="https://fundingradar.ru" target="_blank" rel="noopener noreferrer" className="info-link site">
                    <img src="/logo192.png" alt="CryptoProjects" className="site-logo" /> {t("infoPage.ourSite", "Наш сайт")}
                </a>
                <a href="https://t.me/fundingradar_official" target="_blank" rel="noopener noreferrer" className="info-link telegram">
                    <FaTelegramPlane className="icon" /> {t("infoPage.ourChannel", "Наш канал")}
                </a>
                <a href="https://www.youtube.com/@fundingradar" target="_blank" rel="noopener noreferrer" className="info-link youtube">
                    <FaYoutube className="icon" /> YouTube
                </a>
            </div>
            <h3 className="faq-title">{t("infoPage.usefulLinks", "Полезные ссылки")}</h3>
            <div className="useful-links">
                <a href="https://t.me/xWHOxAMxIx" target="_blank" rel="noopener noreferrer" className="useful-link">
                💬 {t("infoPage.support", "Техподдержка")}
                </a>
                <a href="https://telegra.ph/Arbitrazh-fandinga-Kak-zarabatyvat-bez-riska-i-slozhnyh-strategij-02-05" target="_blank" rel="noopener noreferrer" className="useful-link">
                    📖 {t("infoPage.whatIsFunding", "Что такое фандинг?")}
                </a>
                <a href="https://telegra.ph/Instrukciya-po-botu-dlya-arbitrazha-fandinga-06-06" target="_blank" rel="noopener noreferrer" className="useful-link">
                    🛠 {t("infoPage.botGuide", "Инструкция по боту")}
                </a>
            </div>
            <h3 className="faq-title">{t("infoPage.popularQuestions", "Популярные вопросы")}</h3>
            <div className="faq-container">
                {faqItems.map((item, index) => (
                    <div 
                        key={index} 
                        className={`faq-item ${openIndex === index ? "open" : ""}`} 
                        onClick={() => toggleFAQ(index)}
                    >
                        <div className="faq-question">
                            {item.question}
                            <span className="faq-arrow">{openIndex === index ? "▲" : "▼"}</span>
                        </div>
                        <div className="faq-answer" ref={(el) => (answerRefs.current[index] = el)}>{item.answer}</div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default Info;

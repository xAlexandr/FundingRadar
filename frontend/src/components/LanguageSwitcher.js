import React from "react";
import { useTranslation } from "react-i18next";
import "./LanguageSwitcher.css";

const LanguageSwitcher = () => {
  const { i18n } = useTranslation();
  const currentLang = i18n.language || "ru";

  const toggleLanguage = () => {
    const newLang = currentLang === "ru" ? "en" : "ru";
    i18n.changeLanguage(newLang);
    localStorage.setItem("lang", newLang);
  };

  return (
    <button
      className="lang-switcher"
      onClick={toggleLanguage}
      title={currentLang === "ru" ? "Switch to English" : "Переключить на русский"}
    >
      {currentLang === "ru" ? "EN" : "RU"}
    </button>
  );
};

export default LanguageSwitcher;

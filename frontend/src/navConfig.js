// navConfig.js — легко добавлять новые пункты/подпункты
const navConfig = [
  { key: "home", to: "/", icon: "home", i18nKey: "menu.home" },
  { key: "tarifs", to: "/tarifs", icon: "tarifs", i18nKey: "menu.tarifs" },
  { key: "funding-rates", to: "/funding-rates", icon: "trading", i18nKey: "menu.fundingRates", title: "Funding Spreads" },
  {
    key: "information",
    to: "/information",
    icon: "info",
    i18nKey: "menu.info",
    children: [
      { key: "funding", to: "/information/funding", i18nKey: "menu.funding" },
      { key: "instruction", to: "/information/instruction", i18nKey: "menu.instruction" }
    ]
  },
  { key: "markets", to: "/markets", icon: "markets", i18nKey: "menu.markets" },
  { key: "faq", to: "/faq", icon: "faq", i18nKey: "menu.faq" }
];

export default navConfig;

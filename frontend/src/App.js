import React, { useState, useEffect, createContext, useContext } from 'react';
import { BrowserRouter as Router, Route, Routes, Navigate, Outlet } from 'react-router-dom';
import { authenticateWithTelegram } from './components/auth';
import { HelmetProvider } from "react-helmet-async";
import Home from './components/Home';
import Spreads from './components/Spreads'
import Subscription from './components/Subscription';
import Info from './components/Info';
import Navbar from './components/Navbar'; // Навигация
import Landing from "./components/Landing";
import Preloader from './components/Preloader';
import LayoutWeb from './components/LayoutWeb';
import Pricing from './components/Pricing';
import Faq from './components/Faq';
import FundingIs from './components/FundingIs';
import AboutBot from './components/AboutBot';
import Markets from './components/Markets';
import TopFunding from './components/TopFunding';

// Создаем контекст для аутентификации
export const AuthContext = createContext();

const getTelegramId = (initData) => {
    try {
        const params = new URLSearchParams(initData);
        const userData = params.get("user"); // Получаем закодированный JSON-объект
        if (!userData) return null;

        const userObj = JSON.parse(decodeURIComponent(userData)); // Декодируем и парсим JSON
        return userObj.id || null; // Возвращаем telegram_id
    } catch (error) {
        console.error("Ошибка разбора initData:", error);
        return null;
    }
};

export const AuthProvider = ({ children }) => {
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [authLoading, setAuthLoading] = useState(true); // Состояние загрузки аутентификации
    const [telegramId, setTelegramId] = useState(null);
  //  const [referral, setReferral] = useState(null);

    useEffect(() => {

        //    // Проверяем наличие реферального параметра в URL
        //     const urlParams = new URLSearchParams(window.location.search);
        //     const referralId = urlParams.get("startapp");
        //     console.log("AA", referralId)
        //     if (referralId) {
        //     // Сохраняем реферальный ID в состоянии (можно использовать для отображения или добавления в путь)
        //     setReferral(referralId);
        //     }
        // Skip Telegram SDK loading on public pages (not needed, blocks non-VPN users)
        const path = window.location.pathname;
        const publicPages = ["/", "/landing", "/tarifs", "/funding-rates", "/information/funding", "/information/instruction", "/markets", "/faq"];
        if (publicPages.some(p => path === p || path.startsWith(p + "/"))) {
            setAuthLoading(false);
            return;
        }
            

        const script = document.createElement("script");
        script.src = "https://telegram.org/js/telegram-web-app.js";
        script.async = true;

        // Timeout: if Telegram SDK doesn't load in 5s, continue without it
        const sdkTimeout = setTimeout(() => {
            console.warn("Telegram SDK load timeout — continuing without it");
            setIsAuthenticated(false);
            setAuthLoading(false);
        }, 15000);

        script.onload = () => {
            clearTimeout(sdkTimeout);
            if (window.Telegram?.WebApp) {
                console.log("Telegram WebApp SDK loaded");
                window.Telegram.WebApp.ready();
                window.Telegram.WebApp.expand();
                window.Telegram.WebApp.setHeaderColor("#243036");
                let initData = window.Telegram.WebApp.initData;

                const isDebug = process.env.REACT_APP_DEBUG === 'true';
                if (isDebug && initData == "")
                {
                    // Заглушка для локальной разработки вне Telegram.
                    // Реальные данные Telegram в репозитории не хранятся.
                    initData = 'query_id=DEBUG_QUERY_ID&user=%7B%22id%22%3A0%2C%22first_name%22%3A%22Debug%22%2C%22username%22%3A%22debug_user%22%7D&auth_date=0&hash=DEBUG_HASH'
                }

                authenticateWithTelegram(initData)
                    .then(data => {
                        if (data) {
                            setIsAuthenticated(true);
                            let tg_id = getTelegramId(initData);
                            setTelegramId(tg_id);
                        } else {
                            setIsAuthenticated(false);
                        }
                    })
                    .catch(() => setIsAuthenticated(false))
                    .finally(() => setAuthLoading(false));
            } else {
                console.error("Telegram WebApp SDK not found.");
                setIsAuthenticated(false);
                setAuthLoading(false);
            }
        };

        script.onerror = () => {
            clearTimeout(sdkTimeout);
            console.warn("Telegram SDK failed to load — continuing without it");
            setIsAuthenticated(false);
            setAuthLoading(false);
        };

        document.body.appendChild(script);
    }, []);

    return (
        <AuthContext.Provider value={{ isAuthenticated, authLoading, telegramId }}>
            {children}
        </AuthContext.Provider>
    );
};

function App() {


    const [loading, setLoading] = useState(true); // Состояние загрузки
    const { isAuthenticated, authLoading } = useContext(AuthContext); // Используем контекст
    

    useEffect(() => {

     

    // Массив изображений, которые нужно предзагрузить
    const images = [
      '/images/graph.svg',
      '/images/wallet.svg',
      '/images/info.svg',
      // Добавьте остальные пути к изображениям
    ];

    // Функция предзагрузки изображений
    const preloadImages = (imageArray) => {
      return Promise.all(
        imageArray.map((src) => {
          return new Promise((resolve, reject) => {
            const img = new Image();
            img.src = src;
            img.onload = resolve; // Разрешаем промис, если изображение загружено
            img.onerror = reject; // Отклоняем промис, если произошла ошибка
          });
        })
      );
    };

    // Вызываем функцию предзагрузки изображений
    preloadImages(images)
      .then(() => {
        

        // Добавляем задержку в 1 секунду перед скрытием индикатора загрузки
        setTimeout(() => {
            setLoading(false); // Все изображения успешно загружены, скрываем индикатор загрузки
        }, 300); // Задержка в 1 секунду
      })
      .catch((error) => {
        console.error('Ошибка при загрузке изображений:', error);
        setLoading(false); // Даже если произошла ошибка, скрываем индикатор загрузки
      });
  }, []);

 

// Ожидаем пока загрузятся изображения и произойдет аутентификация
if (loading || authLoading) {
    return <Preloader />; // Показать индикатор загрузки
}


    // Получаем последний выбранный путь из localStorage или стандартный
    const lastTrade = JSON.parse(localStorage.getItem("lastTrade")) || {};
    const defaultPath = `/trade/${lastTrade.spOrFt || "futures"}/${lastTrade.market1 || "Bybit"}/${lastTrade.market2 || "Mexc"}/${lastTrade.coin || "BTC"}/`;
    // Если есть реферальная ссылка, добавляем её в путь
    // const referralPath = referral ? `${defaultPath}?startapp=${referral}` : defaultPath;
    // console.log('REF PATH', referralPath)
    return (
        <AuthProvider>
            <HelmetProvider>
        <Router>
            <Routes>
                {/* Лендинг для SEO, теперь это главная */}
                <Route element={<LayoutWeb />}>
                <Route path="/" element={<Landing />} />
                <Route path="/tarifs" element={<Pricing />} />
                <Route path="/information/funding" element={<FundingIs />} />
                <Route path="/information/instruction" element={<AboutBot />} />
                <Route path="/markets" element={<Markets />} />
                <Route path="/funding-rates" element={<TopFunding />} />
                <Route path="/faq" element={<Faq />} />
                </Route>

                {/* Основная структура с Navbar */}
                <Route element={<Layout />}>
                <Route path="/trade/:spOrFtP/:market1P/:market2P/:coinP/" element={<Home />} />
                <Route path="/spreads" element={<Spreads />} />
                    <Route path="/subscription" element={<Subscription />} />
                    <Route path="/info" element={<Info />} />
                </Route>
            </Routes>
        </Router>
        </HelmetProvider>
        </AuthProvider>
    );
}

// Компонент Layout с навигацией
const Layout = () => {
    return (
        <div>
            <Navbar />
            <Outlet /> {/* Вставляет вложенные маршруты */}
        </div>
    );
};

export default App;

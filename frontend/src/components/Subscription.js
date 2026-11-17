import React, { useEffect, useState, useContext } from "react";
import { useTranslation } from "react-i18next";
import { fetchSubscription } from '../api/api.js';
import "./Subscription.css";
import { AuthContext } from "../App";

const Subscription = () => {
    const { t } = useTranslation();
    const { telegramId } = useContext(AuthContext);
    const [subscription, setSubscription] = useState(null);
    const [referrals, setReferrals] = useState([]);
    const [copied, setCopied] = useState(false);
    const [copiedAddress, setCopiedAddress] = useState(false);
    const [copiedMemo, setCopiedMemo] = useState(false);

    const [showPaymentModal, setShowPaymentModal] = useState(false);
    const tonAddress = "UQBq-z2dTpWbq2rO5JvMxrfmNU_ZheQHQs80k_zA1yPXmk0N"; // Пример
    const [tonMemo, setTonMemo] = useState("error")
    // const tonMemo = "sub1234"; // Уникальный memo, можно менять динамически
    const price = "40 USDT"; // Цена подписки

    

    const loadSubscription = async () => {
        try {
          const sub_info = await fetchSubscription(); // Загружаем список монет
          setSubscription(sub_info);
          setTonMemo(sub_info.memo)
         // console.log(subscription);
          setReferrals(sub_info.referrals);
        //  console.log(sub_info)
        } catch (error) {
          console.error("Ошибка загрузки списка монет:", error);
        }
      };

    useEffect(() => {
        if (telegramId) {
            
            loadSubscription()
            
        }
    }, [telegramId]); // Загружаем данные только когда есть telegramId

    const copyTonAddress = async () => {
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(tonAddress);
            setCopiedAddress(true);
          } else {
            fallbackCopy(tonAddress);
            setCopiedAddress(true);
          }
        } catch (err) {
          console.error("Ошибка копирования адреса:", err);
          fallbackCopy(tonAddress);
          setCopiedAddress(true);
        }
      
        setTimeout(() => setCopiedAddress(false), 2000);
      };
      
      const copyTonMemo = async () => {
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(tonMemo);
            setCopiedMemo(true);
          } else {
            fallbackCopy(tonMemo);
            setCopiedMemo(true);
          }
        } catch (err) {
          console.error("Ошибка копирования memo:", err);
          fallbackCopy(tonMemo);
          setCopiedMemo(true);
        }
      
        setTimeout(() => setCopiedMemo(false), 2000);
      };

   
    const referralLink = `https://t.me/funding_cryptoprojects_bot?start=${telegramId}`;

    const copyToClipboard = async () => {
        // Если Clipboard API доступен, пробуем его
        if (navigator.clipboard && navigator.clipboard.writeText) {
            try {
                await navigator.clipboard.writeText(referralLink);
                setCopied(true);
            } catch (err) {
                console.error("Clipboard API не сработал, пробуем fallback", err);
                setCopied(true);
                fallbackCopy(referralLink);
            }
        } else {
            fallbackCopy(referralLink);
        }
        setTimeout(() => setCopied(false), 2000);
    };
    
    const fallbackCopy = (text) => {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        // Устанавливаем readonly и делаем элемент недоступным для фокуса
        textArea.setAttribute("readonly", "");
        textArea.setAttribute("tabindex", "-1");
        // Скрываем элемент так, чтобы он не был виден и не вызывал клавиатуру
        textArea.style.position = "absolute";
        textArea.style.left = "-9999px";
        textArea.style.opacity = "0";
        document.body.appendChild(textArea);
        // Выделяем текст без явного вызова focus()
        textArea.select();
    
        try {
            document.execCommand("copy");
            
        } catch (err) {
            console.error("Fallback: не удалось скопировать текст", err);
        }
        document.body.removeChild(textArea);
    };

    // Функция для склонения числительных
    const declension = (number, forms) => {
        number = Math.abs(number) % 100;
        const n1 = number % 10;
        if (number > 10 && number < 20) return forms[2];
        if (n1 === 1) return forms[0];
        if (n1 >= 2 && n1 <= 4) return forms[1];
        return forms[2];
    };

    const getRemainingTime = () => {
        if (!subscription) return "Загрузка...";
        
        const now = new Date();

        if (subscription.subscribe_active && subscription.subscribe_end_date) {
            const endDate = new Date(subscription.subscribe_end_date);
            const remainingDays = Math.max(0, Math.ceil((endDate - now) / (1000 * 60 * 60 * 24)));
            const dayWord = declension(remainingDays, ["день", "дня", "дней"]);
            return `${remainingDays} ${dayWord}`;
        }
        
        if (subscription.test_active && subscription.test_end_date) {
            const endDate = new Date(subscription.test_end_date);
            const remainingHours = Math.max(0, Math.ceil((endDate - now) / (1000 * 60 * 60)));
            const hourWord = declension(remainingHours, ["час", "часа", "часов"]);
            return `${remainingHours} ${hourWord}`;
        }
        
        return "0";
    };


    const getProgressPercentage = () => {
        if (!subscription) return 0;
    
        const now = new Date();
    
        if (subscription.subscribe_active && subscription.subscribe_start_date && subscription.subscribe_end_date) {
            const startDate = new Date(subscription.subscribe_start_date);
            const endDate = new Date(subscription.subscribe_end_date);
            const totalDuration = endDate - startDate;
            const remaining = endDate - now;
            return Math.min(100, Math.max(0, (remaining / totalDuration) * 100)); // На убывание
        }
    
        if (subscription.test_active && subscription.test_start_date && subscription.test_end_date) {
            const startDate = new Date(subscription.test_start_date);
            const endDate = new Date(subscription.test_end_date);
            const totalDuration = endDate - startDate;
            const remaining = endDate - now;
            return Math.min(100, Math.max(0, (remaining / totalDuration) * 100)); // На убывание
        }
    
        return 0;
    };

    return (
        <div className="subscription-container">
            <h2>{t("subscription.title")}</h2>
            {telegramId ? (
                <>
                    <div className="subscription-status">
                        <span className={subscription?.is_active_sub ? "active" : "inactive"}>
                            {subscription?.is_active_sub ? t("subscription.active") : t("subscription.inactive")}
                        </span>
                        <span>{t("subscription.remaining")} {getRemainingTime()}</span>
                    </div>
                    <div className="progress-bar">
                        <div className="progress" style={{ width: `${getProgressPercentage()}%` }}></div>
                    </div>
                    <div className="payment-wrapper">
                        <button className="payment-button" onClick={() => setShowPaymentModal(true)}>
                            {t("subscription.payBtn")}
                        </button>
                    </div>
                    <h3>{t("subscription.myReferral")}</h3>
                    <span className="referral-description">{t("subscription.referralDesc")}</span>
                    <div className="referral-link">
                        <input type="text" value={referralLink} readOnly />
                        <button onClick={copyToClipboard}>{copied ? t("subscription.copied") : t("subscription.copy")}</button>
                    </div>

                    <h3 className="referral-title">{t("subscription.invitedUsers")}</h3>
                    {Array.isArray(referrals) && referrals.length > 0 && (
                    <div className="referral-subtitle"><span>Username</span>
                        <span>ID</span>
                        <span>{t("subscription.test")}</span>
                        <span>{t("subscription.subscribe")}</span>
                    </div> )}
                    <ul className="referral-list">
                        {Array.isArray(referrals) && referrals.length > 0 ? (
                            referrals.map((ref) => (
                                <li className="referral-li" key={ref.tgid}>
                                    <span>
                                    {ref.username
                                        ? ref.username.length > 10
                                        ? ref.username.substring(0, 10) + '..'
                                        : ref.username
                                        : 'None'}
                                    </span>
                                    <span>{ref.tgid}</span>
                                    <div className="img-container">
                                    { ref.testActive == 1 ? (
                                        <img src="images/yes.svg" className="img-sub" alt="timeTest" />
                                        ) : ref.timeTest != 'no' ? (
                                        <img src="images/cross-tested.svg" className="img-test" alt="timeTest" />
                                        ) : ref.testActive == 0 ? (
                                        <img src="images/cross.svg" className="img-test" alt="timeTest" />
                                        ) : null }
                                    </div>
                                    { ref.isActiveAdmin == 2 ? (
                                        <img src="images/cross.svg" className="img-test" alt="Subscribe" />
                                        ) : ref.isActiveAdmin == 1 ? (
                                        <img src="images/yes.svg" className="img-sub" alt="Subscribe" />
                                        ) : ref.isActiveAdmin == 0 ? (
                                        <img src="images/cross.svg" className="img-test" alt="Subscribe" />
                                        ) : null }


                                </li>
                            ))
                        ) : (
                            <li>{t("subscription.noInvited")}</li>
                        )}
                    </ul>
                    <div className="fererral-info-container">
                    <div className="referral-output">
                            <img className="info-img" src="/images/info.svg" alt="info"></img>
                            <div>
                            <span>{t("subscription.withdrawInfo")}<br></br><br></br>
                                {t("subscription.withdrawNote")}
                            </span>
                            </div>

                    </div>
                    </div>
                </>
            ) : (
                <p>{t("trade.loading")}</p>
            )}
        {showPaymentModal && (
  <div className="payment-modal" onClick={() => setShowPaymentModal(false)}>
    <div className="payment-modal-content" onClick={(e) => e.stopPropagation()}>
      <button className="close-button" onClick={() => setShowPaymentModal(false)}>×</button>
      <h3>{t("subscription.paymentTitle")}</h3>
      <div className="payment-info">
        <p>{t("subscription.network")}: <strong>TON</strong></p>
        <p>{t("subscription.price")}: <strong>{price}</strong></p>
        </div>

      <div className="payment-address">
        <label>{t("subscription.address")}</label>
        <div className="payment-copy-group">
          <input type="text" value={tonAddress} readOnly />
          <button onClick={copyTonAddress}>
            {copiedAddress ? t("subscription.copied") : t("subscription.copy")}
          </button>
        </div>
      </div>

      <div className="payment-address">
        <label>{t("subscription.memo")}</label>
        <div className="payment-copy-group">
          <input type="text" value={tonMemo} readOnly />
          <button onClick={copyTonMemo}>
            {copiedMemo ? t("subscription.copied") : t("subscription.copy")}
          </button>
        </div>
      </div>

      <p className="payment-warning">
  {t("subscription.paymentNote")}&nbsp;
  <a className="support-link" href="https://t.me/xWHOxAMxIx" target="_blank">@xWHOxAMxIx</a>
</p>
    </div>
  </div>
)}
        </div>
    );
};

export default Subscription;

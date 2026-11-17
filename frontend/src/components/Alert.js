import React, { useState, useEffect } from "react";

const AlertBell = ({ entryPrice, exitPrice }) => {
  const [showModal, setShowModal] = useState(false);
  const [entryAlert, setEntryAlert] = useState(JSON.parse(localStorage.getItem("entryAlert")) ?? "");
  const [exitAlert, setExitAlert] = useState(JSON.parse(localStorage.getItem("exitAlert")) ?? "");
  const [isEntryEnabled, setIsEntryEnabled] = useState(false);
  const [isExitEnabled, setIsExitEnabled] = useState(false);
  const [alertCountEntry, setAlertCountEntry] = useState(0);
  const [alertCountExit, setAlertCountExit] = useState(0);

  useEffect(() => {
    localStorage.setItem("entryAlert", JSON.stringify(entryAlert));
  }, [entryAlert]);

  useEffect(() => {
    localStorage.setItem("exitAlert", JSON.stringify(exitAlert));
  }, [exitAlert]);

  const playAlertEntry = () => {
    if (alertCountEntry < 3) {
        const audio = new Audio("/sound/alert.mp3");
        audio.play();
        setAlertCountEntry(alertCountEntry + 1);
    }
    };
    const playAlertExit = () => {
        if (alertCountExit < 3) {
            const audio = new Audio("/sound/alert.mp3");
            audio.play();
            setAlertCountExit(alertCountExit + 1);
        }
        };


    useEffect(() => {
        const entryAlertNum = parseFloat(entryAlert);
        const exitAlertNum = parseFloat(exitAlert);
        if (isEntryEnabled && !isNaN(entryAlertNum) && entryPrice >= entryAlertNum) {
            playAlertEntry();
        }
        if (isExitEnabled && !isNaN(exitAlertNum) && exitPrice <= exitAlertNum) {
            playAlertExit();
        }
    }, [entryPrice, exitPrice]);


    useEffect(() => {
        if (entryPrice < parseFloat(entryAlert)){
            setAlertCountEntry(0); // Сброс при выходе за границы
        }
      }, [entryPrice]);
    
      useEffect(() => {
        if (exitPrice > parseFloat(exitAlert)) {
            setAlertCountExit(0); // Сброс при выходе за границы
        }
      }, [exitPrice]);

      useEffect(() => {
        setAlertCountEntry(0); // Сброс 
      }, [isEntryEnabled, entryAlert]);
      useEffect(() => {
        setAlertCountExit(0); // Сброс 
      }, [isExitEnabled, exitAlert]);

  const [modalPosition, setModalPosition] = useState({ top: 0, left: 0 });

    const openModal = (event) => {
    const rect = event.target.getBoundingClientRect();
    setModalPosition({ top: rect.top - 70, left: rect.left - 180 }); // Сдвигаем вверх и влево
    setShowModal(true);
    };

  return (
    <>
      <button className={`alert-bell ${isEntryEnabled || isExitEnabled ? "active" : ""}`} onClick={openModal}>
        🔔
      </button>
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" style={{ top: `${modalPosition.top}px`, left: `${modalPosition.left}px` }} onClick={(e) => e.stopPropagation()}>
            <div className="alert-input-block">
              <label>
                <input
                  type="number"
                  value={entryAlert}
                  onChange={(e) => setEntryAlert(e.target.value)}
                  placeholder="Вход"
                />
                <button className={`alert-button ${isEntryEnabled ? "on" : "off"}`} onClick={() => setIsEntryEnabled(!isEntryEnabled)}>
                
                  <span></span>
                </button>
              </label>
              <label>
                <input
                  type="number"
                  value={exitAlert}
                  onChange={(e) => setExitAlert(e.target.value)}
                  placeholder="Выход"
                />
                <button className={`alert-button ${isExitEnabled ? "on" : "off"}`} onClick={() => setIsExitEnabled(!isExitEnabled)}>
                  <span></span>
                  
                </button>
              </label>
            </div>
            
          </div>
        </div>
      )}
    </>
  );
};

export default AlertBell;

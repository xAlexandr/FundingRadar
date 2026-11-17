import axiosInstance from './axiosConfig';

export const fetchData = async (sp_or_ft, market1, market2, coin) => {
    try {
        const formData = new FormData();
        formData.append('sp_or_ft', sp_or_ft);
        formData.append('market1', market1);
        formData.append('market2', market2);
        formData.append('coin', coin);

        const response = await axiosInstance.post('getdata/', formData, {
            headers: {
                'Content-Type': 'multipart/form-data',  // Исправлен Content-Type
            },
        });

        return response.data;
    } catch (error) {
      //  console.log(error.status)
        if (error.status != 200 && error.status != 500) {
            return 403;
        } else {
            console.error('Ошибка при загрузке данных:', error);
            return null;
        }
        
    }
};

export const fetchCoinList = async () => {
    try {
        const response = await axiosInstance.get("coins/"); // Укажите правильный URL API
        const data = response.data.coins; // Получаем объект монет
     //   console.log(data);

        // Получаем массив символов монет (ключи объекта)
        const data_coins = Object.keys(data);
      //  console.log(data_coins);

        return data_coins; // Возвращаем массив монет
    } catch (error) {
        console.error("Ошибка при получении списка монет:", error);
        return [];
    }
};


export const fetchSubscription = async () => {
    try {
        const response = await axiosInstance.get(`get_subscribe/`);
        const data = response.data;
        return data;
    } catch (err) {
        console.error("Ошибка загрузки подписки:", err);
        return null;
    }
};


export const fetchDepthValueSet = async (depth_value) => {
    try {
        const formData = new FormData();
        formData.append('depth_value', depth_value)
        const response = await axiosInstance.post("update-depth/", formData, {
            headers: {
                'Content-Type': 'multipart/form-data',  // Исправлен Content-Type
            },
        }); // Укажите правильный URL API
        return response.data; // Получаем объект монет
       
    } catch (error) {
        console.error('Ошибка при загрузке данных depth:', error);
        return null;
    }
}

export const fetchFuturesAll = async (page, items, sort, lt) => {
    try {
      //  console.log(`get_futures/?page=${page}`)
        const ltParam = lt ? "1" : "0";
        const response = await axiosInstance.get(`get_futures/?page=${page}&items=${items}&sort=${sort}&lt=${ltParam}`);
      //  console.log('response', response)
        const data = response.data;
        return data;
    } catch (err) {
        console.error("Ошибка загрузки подписки:", err);
        return null;
    }
}

export const fetchFuturesPage = async (symbol, items, sort, lt) => {
    try {
        const ltParam = lt ? "1" : "0";
        const response = await axiosInstance.get(`get_futures_pages/?symbol=${symbol}&items=${items}&sort=${sort}&lt=${ltParam}`);
        const data = response.data;
        return data;
    } catch (err) {
        console.error("Ошибка загрузки подписки:", err);
        return null;
    }
}

export const fetchFuturesId = async (symbol, market1, market2) => {
    try {
        const response = await axiosInstance.get(`get_futures_id/?symbol=${symbol}&m1=${market1}&m2=${market2}`);
        const data = response.data;
        return data;
    } catch (err) {
        console.error("Ошибка загрузки подписки:", err);
        return null;
    }
}

export const fetchSpotAll = async (page, items, sort, lt) => {
    try {
      //  console.log(`get_futures/?page=${page}`)
        const ltParam = lt ? "1" : "0";
        const response = await axiosInstance.get(`get_spot/?page=${page}&items=${items}&sort=${sort}&lt=${ltParam}`);
      //  console.log('response', response)
        const data = response.data;
        return data;
    } catch (err) {
        console.error("Ошибка загрузки подписки:", err);
        return null;
    }
}

export const fetchSpotPage = async (symbol, items, sort, lt) => {
    try {
        const ltParam = lt ? "1" : "0";
        const response = await axiosInstance.get(`get_spot_pages/?symbol=${symbol}&items=${items}&sort=${sort}&lt=${ltParam}`);
        const data = response.data;
        return data;
    } catch (err) {
        console.error("Ошибка загрузки подписки:", err);
        return null;
    }
}

export const fetchSpotId = async (symbol, market1, market2) => {
    try {
        const response = await axiosInstance.get(`get_spot_id/?symbol=${symbol}&m1=${market1}&m2=${market2}`);
        const data = response.data;
        return data;
    } catch (err) {
        console.error("Ошибка загрузки подписки:", err);
        return null;
    }
}

export const fetchChangeToSpread = async () => {
    try {
        const response = await axiosInstance.get(`get_change_to_spread/`);
        const data = response.data;
        return data;
    } catch (err) {
        console.error("Ошибка загрузки подписки:", err);
        return null;
    }
}
export const fetchChangeToCourse = async () => {
    try {
        const response = await axiosInstance.get(`get_change_to_course/`);
        const data = response.data;
        return data;
    } catch (err) {
        console.error("Ошибка загрузки подписки:", err);
        return null;
    }
}
export const fetchChangeToBig = async () => {
    try {
        const response = await axiosInstance.get(`get_change_to_big/`);
        const data = response.data.result;
        return data;
    } catch (err) {
        console.error("Ошибка загрузки подписки:", err);
        return null;
    }
}
export const fetchSettings = async () => {
    try {
        const response = await axiosInstance.get(`get_data_settings/`);
        const data = response.data;
        return data;
    } catch (err) {
        console.error("Ошибка загрузки подписки:", err);
        return null;
    }
}

export const fetchDexAll = async (page, items, sort, lt) => {
    try {
        const ltParam = lt ? "1" : "0";
        const response = await axiosInstance.get(`get_dex/?page=${page}&items=${items}&sort=${sort || 'spread'}&lt=${ltParam}`);
        return response.data;
    } catch (err) {
        console.error("Ошибка загрузки DEX:", err);
        return null;
    }
}

export const fetchDexPage = async (symbol, items, sort, lt) => {
    try {
        const ltParam = lt ? "1" : "0";
        const response = await axiosInstance.get(`get_dex_pages/?symbol=${symbol}&items=${items}&sort=${sort || 'spread'}&lt=${ltParam}`);
        return response.data;
    } catch (err) {
        console.error("Ошибка загрузки DEX pages:", err);
        return null;
    }
}

export const fetchDexId = async (symbol, market) => {
    try {
        const response = await axiosInstance.get(`get_dex_id/?symbol=${symbol}&market=${market || ''}`);
        return response.data;
    } catch (err) {
        console.error("Ошибка загрузки DEX id:", err);
        return null;
    }
}

export const fetchTopFunding = async () => {
    try {
        const response = await axiosInstance.get(`top-funding/`);
        return response.data;
    } catch (err) {
        console.error("Ошибка загрузки top funding:", err);
        return null;
    }
}

export const fetchTopFundingSpot = async () => {
    try {
        const response = await axiosInstance.get(`top-funding-spot/`);
        return response.data;
    } catch (err) {
        console.error("Ошибка загрузки top funding spot:", err);
        return null;
    }
}
import axiosInstance from '../api/axiosConfig';

const retryAsync = async (fn, retries = 2, delay = 1000) => {
  for (let i = 0; i <= retries; i++) {
    try {
      return await fn();
    } catch (err) {
      if (i === retries) throw err;
      await new Promise(r => setTimeout(r, delay * (i + 1)));
    }
  }
};

export const authenticateWithTelegram = async (initData) => {
    try {
      const response = await retryAsync(() =>
        axiosInstance.post('/auth/telegram/', initData, {
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
          },
        })
      );

      const data = await response.data;

      localStorage.setItem('accessToken', data.access);
      localStorage.setItem('refreshToken', data.refresh);
      return data;
    } catch (error) {
      console.error("Ошибка аутентификации с Telegram:", error);
    }
  };
  
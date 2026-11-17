// import axios from 'axios';


// const refreshAccessToken = async () => {
//   const refreshToken = localStorage.getItem('refreshToken');
//   if (!refreshToken) {
//     console.error("Refresh token отсутствует");
//     return;
//   }

//   try {
//     const response = await axios.post('/api/token/refresh/', { refresh: refreshToken });
//     const { access } = response.data;
//     console.log('newtoken2', access)
//     // Сохраняем новый токен
//     localStorage.setItem('accessToken', access);
//   } catch (error) {
//     console.error("Ошибка обновления токена:", error.response?.data);
//   }
// };

// // Создаем экземпляр axios с базовым URL, который будет проксироваться
// const axiosInstance = axios.create({
//   // baseURL: '', // Теперь это будет проксироваться на ваш Django сервер
// });

// // Перехватчик запросов для добавления токена в заголовок
// axiosInstance.interceptors.request.use(
//   (config) => {
//     const token = localStorage.getItem('accessToken'); // Получаем токен из localStorage
//     if (token) {
//       config.headers.Authorization = `Bearer ${token}`; // Добавляем токен в заголовок
//     }
//     return config;
//   },
//   (error) => Promise.reject(error)
// );

// // Перехватчик ответов для обработки ошибок
// axiosInstance.interceptors.response.use(
//   (response) => response, // Возвращаем успешный ответ
//   async (error) => {
//     const originalRequest = error.config; // Сохраняем оригинальный запрос

//     // Если ошибка 401, попробуем обновить токен
//     if (error.response.status === 401) {
//       console.error("Unauthorized - пытаемся обновить токен");

//       const newAccessToken = await refreshAccessToken(); // Обновляем токен

//       if (newAccessToken) {
//         // Если токен успешно обновлен, обновляем заголовок Authorization и повторяем оригинальный запрос
//         originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
//         return axiosInstance(originalRequest); // Повторяем запрос
//       } else {
//         const telegram_id_axios = localStorage.getItem('telegram_id');
//         // Если обновление токена не удалось, можем обработать это, например, перенаправить на страницу входа
//         console.error("Не удалось обновить токен, перенаправляем на страницу входа");
//           // Удаляем токены из localStorage при ошибке
//         localStorage.removeItem('accessToken');
//         localStorage.removeItem('refreshToken');
//         const response = await axios.post('/api/token/', { telegram_id: telegram_id_axios});
//         console.log('req api token', response)
//         const { access, refresh } = response.data;

//         localStorage.setItem('accessToken', access);
//         localStorage.setItem('refreshToken', refresh);

//       }
//     }

//     return Promise.reject(error); // Если это не 401 или не удалось обновить токен, просто отклоняем промис
//   }
// );

// export default axiosInstance;


import axios from 'axios';

const isDebug = process.env.REACT_APP_DEBUG === 'true';

// Локальный или прод-адрес
const API_URL = isDebug
  ? process.env.REACT_APP_API_URL
  : process.env.REACT_APP_API_URL_PROD;

//const API_URL = process.env.REACT_APP_API_URL || 'http://0.0.0.0:8000/api/';
//const API_URL = 'https://cp-bot.ru:8000/api/'; // на хостинг
// Функция обновления access-токена
const refreshAccessToken = async () => {
  const refreshToken = localStorage.getItem('refreshToken');
  if (!refreshToken) {
    console.error("Refresh token отсутствует");
    return null; // Важно возвращать null, а не undefined
  }

  try {
    const response = await axios.post(`${API_URL}token/refresh/`, { refresh: refreshToken });
    const { access } = response.data;
    
    // Сохраняем новый токен
    localStorage.setItem('accessToken', access);
    return access;  // Возвращаем обновленный токен
  } catch (error) {
    console.error("Ошибка обновления токена:", error.response?.data);
    return null;
  }
};

// Создаем экземпляр axios с базовым URL
const axiosInstance = axios.create({
  baseURL: API_URL, // Добавлен baseURL
  headers: {
    'Content-Type': 'application/json',
  }
});

// Перехватчик запросов для добавления токена в заголовок
axiosInstance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('accessToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Перехватчик ответов для обработки ошибок аутентификации (401)
axiosInstance.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;  // Флаг, чтобы избежать зацикливания

      const newAccessToken = await refreshAccessToken(); // Запрашиваем новый access-токен

      if (newAccessToken) {
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return axiosInstance(originalRequest); // Повторяем запрос с новым токеном
      }

      // Если обновление не удалось, удаляем токены и пробуем заново аутентифицировать пользователя
      console.error("Не удалось обновить токен, перенаправляем на страницу входа");
      localStorage.removeItem('accessToken');
      localStorage.removeItem('refreshToken');

      const telegram_id = localStorage.getItem('telegram_id');
      if (!telegram_id) {
        console.error("Нет telegram_id, невозможно повторно войти.");
        return Promise.reject(error);
      }

      try {
        const response = await axios.post(`${API_URL}token/`, { telegram_id });
        const { access, refresh } = response.data;

        localStorage.setItem('accessToken', access);
        localStorage.setItem('refreshToken', refresh);

        originalRequest.headers.Authorization = `Bearer ${access}`;
        return axiosInstance(originalRequest); // Повторяем оригинальный запрос
      } catch (reAuthError) {
        console.error("Ошибка повторной аутентификации:", reAuthError.response?.data);
        return Promise.reject(reAuthError);
      }
    }

    return Promise.reject(error);
  }
);

export default axiosInstance;

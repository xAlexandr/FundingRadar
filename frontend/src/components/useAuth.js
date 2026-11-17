// useAuth.js - Хук для получения состояния аутентификации
import { useContext } from 'react';
import { AuthContext } from '../App.js';  // Путь, где находится контекст

const useAuth = () => {
    return useContext(AuthContext);
};

export default useAuth;

// src/setupProxy.js
const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  // Берём из окружения (string!)

  app.use(
    '/api', // Все запросы, начинающиеся с /api, будут проксированы
    createProxyMiddleware({
       target: 'http://127.0.0.1:8000/api/',
      // target: 'http://django-app`:8000/api/',
    //  target: 'https://127.0.0.1:8000', // На хостинг
      changeOrigin: true,
    })
  );
};
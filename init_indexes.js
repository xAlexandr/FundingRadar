// init_indexes_ttl.js
db = db.getSiblingDB("funding");

// TTL в секундах (48 часов)
const ttl_seconds = 48 * 60 * 60;

// Создание обычных индексов (если нет)
db.futures.createIndex({ exchange_name: 1, symbol: 1, datetime: 1 });
db.spot.createIndex({ exchange_name: 1, symbol: 1, datetime: 1 });

// TTL индексы
db.futures.createIndex(
  { datetime: 1 },
  { expireAfterSeconds: ttl_seconds }
);

db.spot.createIndex(
  { datetime: 1 },
  { expireAfterSeconds: ttl_seconds }
);

print("✅ TTL индексы и обычные индексы успешно созданы/обновлены.");
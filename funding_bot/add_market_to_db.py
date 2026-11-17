import mysql.connector
import json
import os
# Новый список базовых бирж
base_markets = [
    'Bybit_1', 'Mexc_1', 'Kucoin_1', 'Gateio_1', 'Bitget_1',
    'Huobi_1', 'Okx_1', 'Binance_1', 'BingX_1', 'BitMart_1',
    'Ourbit_1', 'Hyperliquid_1', 'LBank_1', 'DEX_1', 'Aster_1', 'XT_1',
    'CoinEx_1', 'WEEX_1', 'Phemex_1', 'BinanceAlpha_1'
]
host = os.getenv('DB_HOST', 'mysql')
user = os.getenv('MYSQL_USER', 'username')
password = os.getenv('MYSQL_PASSWORD', 'password')
database = os.getenv('MYSQL_DATABASE', 'funding')
# Подключение к MySQL
connection = mysql.connector.connect(
    host=host,
    user=user,
    password=password,
    database=database
)
cursor = connection.cursor(dictionary=True)  # dictionary=True чтобы имена полей были в ключах

# Получаем всех пользователей
cursor.execute("SELECT id, listMarketsSpot, listMarketsFutures FROM Users")
accounts = cursor.fetchall()

for acc in accounts:
    # Декодируем текущие настройки (если пусто — пустой список)
    try:
        current_spot = json.loads(acc['listMarketsSpot']) if acc['listMarketsSpot'] else []
    except:
        current_spot = []

    try:
        current_futures = json.loads(acc['listMarketsFutures']) if acc['listMarketsFutures'] else []
    except:
        current_futures = []

    # Функция для обновления списка с сохранением _0/_1
    def update_markets(old_list):
        new_list = []
        for market in base_markets:
            name, default_status = market.split('_')
            found = False
            for old in old_list:
                if old.startswith(name + '_'):
                    new_list.append(old)  # сохраняем как было (_0 или _1)
                    found = True
                    break
            if not found:
                new_list.append(market)  # добавляем дефолтное значение
        return new_list

    new_spot = update_markets(current_spot)
    new_futures = update_markets(current_futures)

    # Записываем обратно в БД
    cursor.execute("""
        UPDATE Users 
        SET listMarketsSpot = %s, listMarketsFutures = %s 
        WHERE id = %s
    """, (json.dumps(new_spot), json.dumps(new_futures), acc['id']))

connection.commit()
cursor.close()
connection.close()

print("Обновление завершено.")

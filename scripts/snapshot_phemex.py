import asyncio
import aiohttp
import json
from pathlib import Path
from datetime import datetime

PROXY = "socks5://127.0.0.1:2080"  # при необходимости укажите свой прокси

# Phemex endpoints (публичные, без ключей)
PHEMEX_FUT_TICKER_URL = 'https://api.phemex.com/md/v3/ticker/24hr/all'
PHEMEX_SPOT_TICKER_URL = 'https://api.phemex.com/md/v3/spot/ticker/24hr/all'
PHEMEX_REAL_FUNDING_URL = 'https://api.phemex.com/contract-biz/public/real-funding-rates'
PHEMEX_PRODUCTS_URL = 'https://api.phemex.com/public/products'  # добавлено

# Папка для сохранения фикстур
BASE_DIR = Path("../funding_bot/tests/fixtures/phemex")
BASE_DIR.mkdir(parents=True, exist_ok=True)


def save_json(name: str, data: dict | list):
    """Сохраняет данные в JSON-файл с отступами."""
    path = BASE_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def timestamp():
    return datetime.utcnow().isoformat()


async def fetch(session, url):
    """GET-запрос с прокси."""
    async with session.get(url, proxy=PROXY, timeout=20) as r:
        return await r.json()


async def snapshot_phemex():
    async with aiohttp.ClientSession() as session:
        print("📡 Fetching Phemex products (public/products)...")
        products = await fetch(session, PHEMEX_PRODUCTS_URL)

        print("📡 Fetching Phemex futures ticker (24hr all)...")
        fut_ticker = await fetch(session, PHEMEX_FUT_TICKER_URL)

        print("📡 Fetching Phemex spot ticker (24hr all)...")
        spot_ticker = await fetch(session, PHEMEX_SPOT_TICKER_URL)

        print("📡 Fetching Phemex real funding rates...")
        funding = await fetch(session, PHEMEX_REAL_FUNDING_URL)

        # Простая валидация
        for name, data in [
            ("products", products),
            ("fut_ticker", fut_ticker),
            ("spot_ticker", spot_ticker),
            ("funding", funding),
        ]:
            if not isinstance(data, (list, dict)):
                print(f"⚠️ {name} response is not list/dict: {type(data)}")

        # Сохраняем сырые ответы
        save_json("products.json", products)
        save_json("futures_ticker.json", fut_ticker)
        save_json("spot_ticker.json", spot_ticker)
        save_json("funding.json", funding)

        # Статистика
        fut_count = len(fut_ticker.get("result", [])) if isinstance(fut_ticker, dict) else 0
        spot_count = len(spot_ticker.get("result", [])) if isinstance(spot_ticker, dict) else 0
        funding_count = len(funding) if isinstance(funding, list) else 0
        products_count = len(products.get("result", {}).get("products", [])) if isinstance(products, dict) else 0

        meta = {
            "created_at": timestamp(),
            "products_count": products_count,
            "futures_ticker_count": fut_count,
            "spot_ticker_count": spot_count,
            "funding_count": funding_count,
            "source": "phemex public api"
        }
        save_json("_meta.json", meta)

        print(f"✅ Snapshots saved to tests/fixtures/phemex/")
        print(f"   Products: {products_count} entries")
        print(f"   Futures: {fut_count} symbols, Spot: {spot_count} symbols, Funding: {funding_count} entries")


if __name__ == "__main__":
    asyncio.run(snapshot_phemex())
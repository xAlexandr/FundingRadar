import asyncio
import aiohttp
import json
from pathlib import Path
from datetime import datetime

PROXY = "socks5://127.0.0.1:2080"
# Фьючерсные эндпоинты WEEX (capi/v3)
WEEX_FUT_TICKER_URL = 'https://api-contract.weex.com/capi/v3/market/ticker/24hr'
WEEX_FUNDING_URL = 'https://api-contract.weex.com/capi/v3/market/premiumIndex'
WEEX_BOOK_URL = 'https://api-contract.weex.com/capi/v3/market/ticker/bookTicker'
WEEX_EXCHANGE_INFO_URL = 'https://api-contract.weex.com/capi/v3/market/exchangeInfo'

# Спотовые эндпоинты WEEX (api/v3)
WEEX_SPOT_BOOK_URL = 'https://api-spot.weex.com/api/v3/market/ticker/bookTicker'
WEEX_SPOT_24HR_URL = 'https://api-spot.weex.com/api/v3/market/ticker/24hr'

BASE_DIR = Path("../funding_bot/tests/fixtures/weex")
BASE_DIR.mkdir(parents=True, exist_ok=True)


def save_json(name: str, data: dict):
    path = BASE_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def timestamp():
    return datetime.utcnow().isoformat()


async def fetch(session, url):
    async with session.get(url, proxy=PROXY, timeout=20) as r:
        return await r.json()


async def snapshot_weex():
    async with aiohttp.ClientSession() as session:

        print("📡 Fetching WEEX futures ticker (24hr)...")
        fut_ticker = await fetch(session, WEEX_FUT_TICKER_URL)

        print("📡 Fetching WEEX funding (premiumIndex)...")
        funding = await fetch(session, WEEX_FUNDING_URL)

        print("📡 Fetching WEEX book (bookTicker)...")
        book = await fetch(session, WEEX_BOOK_URL)

        print("📡 Fetching WEEX exchange info...")
        exchange_info = await fetch(session, WEEX_EXCHANGE_INFO_URL)

        print("📡 Fetching WEEX spot book...")
        spot_book = await fetch(session, WEEX_SPOT_BOOK_URL)

        print("📡 Fetching WEEX spot 24hr...")
        spot_24hr = await fetch(session, WEEX_SPOT_24HR_URL)

        # Простая валидация типов ответов (на случай ошибок)
        for name, data in [
            ("fut_ticker", fut_ticker),
            ("funding", funding),
            ("book", book),
            ("exchange_info", exchange_info),
            ("spot_book", spot_book),
            ("spot_24hr", spot_24hr),
        ]:
            if not isinstance(data, (list, dict)):
                print(f"⚠️ {name} response is not list/dict: {type(data)}")

        # Сохраняем все сырые ответы
        save_json("futures_ticker.json", fut_ticker)
        save_json("funding.json", funding)
        save_json("book.json", book)
        save_json("exchange_info.json", exchange_info)
        save_json("spot_book.json", spot_book)
        save_json("spot_24hr.json", spot_24hr)

        # Мета-файл с краткой статистикой
        meta = {
            "created_at": timestamp(),
            "futures_ticker_count": len(fut_ticker) if isinstance(fut_ticker, list) else 0,
            "funding_count": len(funding) if isinstance(funding, list) else 0,
            "book_count": len(book) if isinstance(book, list) else 0,
            "exchange_info_symbols": len(exchange_info.get("symbols", [])) if isinstance(exchange_info, dict) else 0,
            "spot_book_count": len(spot_book) if isinstance(spot_book, list) else 0,
            "spot_24hr_count": len(spot_24hr) if isinstance(spot_24hr, list) else 0,
            "source": "weex v3 api"
        }
        save_json("_meta.json", meta)

        print("✅ Snapshots saved to tests/fixtures/weex/")


if __name__ == "__main__":
    asyncio.run(snapshot_weex())
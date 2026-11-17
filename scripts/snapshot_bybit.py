import asyncio
import aiohttp
import json
from pathlib import Path
from datetime import datetime

BYBIT_FUT_URL = "https://api.bybit.com/v5/market/tickers?category=linear"
BYBIT_SPOT_URL = "https://api.bybit.com/v5/market/tickers?category=spot"

BASE_DIR = Path("../funding_bot/tests/fixtures/bybit")
BASE_DIR.mkdir(parents=True, exist_ok=True)


def save_json(name: str, data: dict):
    path = BASE_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def timestamp():
    return datetime.utcnow().isoformat()


async def fetch(session, url):
    async with session.get(url, timeout=20) as r:
        return await r.json()


async def snapshot_bybit():
    async with aiohttp.ClientSession() as session:

        print("📡 Fetching Bybit futures...")
        fut = await fetch(session, BYBIT_FUT_URL)

        print("📡 Fetching Bybit spot...")
        spot = await fetch(session, BYBIT_SPOT_URL)

        # --- validation ---
        if not isinstance(fut, dict):
            raise ValueError("Futures response invalid")
        if not isinstance(spot, dict):
            raise ValueError("Spot response invalid")

        # --- save raw snapshots ---
        save_json("futures.json", fut)
        save_json("spot.json", spot)

        # --- optional debug snapshots ---
        if fut.get("result", {}).get("list"):
            print(f"✔ futures symbols: {len(fut['result']['list'])}")

        if spot.get("result", {}).get("list"):
            print(f"✔ spot symbols: {len(spot['result']['list'])}")

        # --- meta file (очень полезно) ---
        meta = {
            "created_at": timestamp(),
            "futures_count": len(fut.get("result", {}).get("list", [])),
            "spot_count": len(spot.get("result", {}).get("list", [])),
            "source": "bybit v5 api"
        }

        save_json("_meta.json", meta)

        print("✅ Snapshot saved to tests/fixtures/bybit/")


if __name__ == "__main__":
    asyncio.run(snapshot_bybit())
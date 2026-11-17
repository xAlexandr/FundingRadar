import asyncio
import aiohttp
import json
import os
from pathlib import Path
from datetime import datetime

# ===== XT API endpoints =====
XT_FUT_URL = "https://fapi.xt.com/future/market/v1/public/cg/contracts"
XT_SPOT_URL = "https://sapi.xt.com/v4/public/ticker"

# Прокси (можно задать через переменную окружения PROXY_XT или PROXY)
PROXY = "socks5://127.0.0.1:2080"

# Папка для сохранения фикстур
BASE_DIR = Path(__file__).resolve().parent.parent / "funding_bot" / "tests" / "fixtures" / "xt"
BASE_DIR.mkdir(parents=True, exist_ok=True)


def save_json(name: str, data: dict):
    """Сохраняет JSON-данные в файл."""
    path = BASE_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def timestamp():
    """Возвращает текущую временную метку в ISO формате."""
    return datetime.utcnow().isoformat()


async def fetch(session, url, proxy=None, retries=2):
    """Выполняет GET-запрос с возможным прокси и повторными попытками."""
    for attempt in range(retries + 1):
        try:
            async with session.get(url, proxy=proxy, timeout=30) as r:
                if r.status != 200:
                    text = await r.text()
                    raise ValueError(f"HTTP {r.status} for {url}: {text[:200]}")
                return await r.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == retries:
                raise
            print(f"⚠️ Attempt {attempt + 1} failed: {e}. Retrying...")
            await asyncio.sleep(1)
        except Exception as e:
            raise


async def snapshot_xt():
    """Создаёт снапшоты ответов XT API для тестов."""
    print(f"🌐 Using proxy: {PROXY if PROXY else 'None (direct)'}")
    async with aiohttp.ClientSession() as session:
        print("📡 Fetching XT futures...")
        fut = await fetch(session, XT_FUT_URL, proxy=PROXY)

        print("📡 Fetching XT spot...")
        spot = await fetch(session, XT_SPOT_URL, proxy=PROXY)

        # --- базовые проверки ---
        if not isinstance(fut, list):
            raise ValueError("Futures response is not a list")
        if not isinstance(spot, dict) or "result" not in spot:
            raise ValueError("Spot response missing 'result' field")

        # --- сохранение сырых ответов ---
        save_json("futures.json", fut)
        save_json("spot.json", spot)

        print(f"✔ futures contracts: {len(fut)}")
        print(f"✔ spot symbols: {len(spot.get('result', []))}")

        # --- мета-файл ---
        meta = {
            "created_at": timestamp(),
            "futures_count": len(fut),
            "spot_count": len(spot.get("result", [])),
            "source": "XT.com API",
            "futures_endpoint": XT_FUT_URL,
            "spot_endpoint": XT_SPOT_URL,
            "proxy_used": PROXY if PROXY else "none",
        }
        save_json("_meta.json", meta)

        print("✅ Snapshot saved to tests/fixtures/xt/")


if __name__ == "__main__":
    asyncio.run(snapshot_xt())
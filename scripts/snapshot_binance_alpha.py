import asyncio
import aiohttp
import json
from pathlib import Path
from datetime import datetime

# ===== Binance Alpha API endpoint (только спот) =====
BINANCE_ALPHA_URL = "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list"

# Прокси (можно задать через окружение или оставить None)
PROXY = None  # или "socks5://127.0.0.1:2080" если нужно

# Папка для фикстур
BASE_DIR = Path(__file__).resolve().parent.parent / "funding_bot" / "tests" / "fixtures" / "binance_alpha"
BASE_DIR.mkdir(parents=True, exist_ok=True)

def save_json(name: str, data: dict | list):
    with open(BASE_DIR / name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def timestamp() -> str:
    return datetime.utcnow().isoformat()

async def fetch(session, url, proxy=None, retries=2):
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
            print(f"⚠️ Attempt {attempt+1} failed: {e}. Retrying...")
            await asyncio.sleep(1)

async def snapshot():
    print(f"🌐 Using proxy: {PROXY if PROXY else 'None (direct)'}")
    async with aiohttp.ClientSession() as session:
        print("📡 Fetching Binance Alpha tokens...")
        data = await fetch(session, BINANCE_ALPHA_URL, proxy=PROXY)

        # Базовая проверка структуры
        if not isinstance(data, dict) or "data" not in data:
            raise ValueError("Invalid response: missing 'data' field")
        tokens = data["data"]
        if not isinstance(tokens, list):
            raise ValueError("Response 'data' is not a list")

        # Сохраняем сырой ответ
        save_json("tokens.json", data)

        print(f"✔ tokens received: {len(tokens)}")

        # Мета-файл
        meta = {
            "created_at": timestamp(),
            "tokens_count": len(tokens),
            "source": "Binance Alpha API (spot only)",
            "endpoint": BINANCE_ALPHA_URL,
            "proxy_used": PROXY if PROXY else "none",
        }
        save_json("_meta.json", meta)

        print("✅ Snapshot saved to tests/fixtures/binance_alpha/")

if __name__ == "__main__":
    asyncio.run(snapshot())
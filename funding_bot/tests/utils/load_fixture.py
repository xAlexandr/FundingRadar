import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent / "fixtures"

def load_fixture(path: str):
    full_path = BASE_DIR / path
    with open(full_path, "r", encoding="utf-8") as f:
        return json.load(f)
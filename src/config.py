from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

BASE_URL = "https://groupwap.eastmoney.com"

PLAYER_LIST_URL = f"{BASE_URL}/group/invest/reality.html"
PLAYER_INFO_URL = f"{BASE_URL}/group/reality/info.html"
POSITION_URL = f"{BASE_URL}/group/reality/detail.html"
TRADE_URL = f"{BASE_URL}/group/reality/change.html"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE_URL,
}
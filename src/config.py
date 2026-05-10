from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

BASE_URL = "https://groupwap.eastmoney.com"

PLAYER_LIST_URL = f"{BASE_URL}/group/invest/reality.html"
PLAYER_INFO_URL = f"{BASE_URL}/group/reality/info.html"
POSITION_URL = f"{BASE_URL}/group/reality/detail.html"
TRADE_URL = f"{BASE_URL}/group/reality/change.html"

# groupwap.eastmoney.com 是东方财富 APP 内嵌 H5 站点。
# 站点 JS 通过 (UA 含 EMProjJs / EMRead 关键字) + (window.emh5 桥接对象存在) 判定 "在 APP 内"。
# 任一条件不满足就弹"前往东方财富APP"对话框，不渲染 detail-content。
# 所以 UA 伪装为东方财富 iPhone WebView，并在 BrowserContext 中注入 emh5 占位桥接。
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
)

# 移动设备模拟参数（与 USER_AGENT 配套，同时给 Playwright 和 requests 使用）
MOBILE_VIEWPORT = {"width": 414, "height": 896}
DEVICE_SCALE_FACTOR = 3

HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": BASE_URL,
}
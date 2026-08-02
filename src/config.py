import os
from pathlib import Path

# 自动加载 .env（如果有 python-dotenv）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _env_int(key: str, default: int) -> int:
    """安全读取整数型环境变量，非法值 fallback 到默认值。"""
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        import warnings
        warnings.warn(f"{key}={raw!r} 不是合法整数，使用默认值 {default}")
        return default


# ─────────────── 基础路径 ───────────────
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = Path(os.getenv("CRAWL_DATA_DIR", BASE_DIR / "data"))
LOG_DIR = Path(os.getenv("CRAWL_LOG_DIR", BASE_DIR / "logs"))
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# ─────────────── 站点 URL ───────────────
BASE_URL = "https://groupwap.eastmoney.com"

PLAYER_LIST_URL = f"{BASE_URL}/group/invest/reality.html"
PLAYER_INFO_URL = f"{BASE_URL}/group/reality/info.html"
POSITION_URL = f"{BASE_URL}/group/reality/detail.html"
TRADE_URL = f"{BASE_URL}/group/reality/change.html"

# ─────────────── 反检测 User-Agent ───────────────
# groupwap.eastmoney.com 是东方财富 APP 内嵌 H5 站点。
# 站点 JS 通过 (UA 含 EMProjJs / EMRead 关键字) + (window.emh5 桥接对象存在) 判定 "在 APP 内"。
# 任一条件不满足就弹"前往东方财富APP"对话框，不渲染 detail-content。
# 所以 UA 伪装为东方财富 iPhone WebView，并在 BrowserContext 中注入 emh5 占位桥接。
_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
)
USER_AGENT = os.getenv("CRAWL_USER_AGENT", _USER_AGENT)

# 移动设备模拟参数（与 USER_AGENT 配套）
MOBILE_VIEWPORT = {"width": 414, "height": 896}
DEVICE_SCALE_FACTOR = 3

HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": BASE_URL,
}

# ─────────────── 代理（从环境变量读取，国内腾讯云可直连不配） ───────────────
HTTP_PROXY = os.getenv("HTTP_PROXY", "") or os.getenv("http_proxy", "")
HTTPS_PROXY = os.getenv("HTTPS_PROXY", "") or os.getenv("https_proxy", "")
SOCKS_PROXY = os.getenv("SOCKS_PROXY", "")

# ─────────────── 运行参数（支持环境变量覆盖） ───────────────
DEFAULT_WORKERS = _env_int("CRAWL_WORKERS", 20)
DEFAULT_LIMIT = _env_int("CRAWL_LIMIT", 500)
BATCH_SIZE = _env_int("CRAWL_BATCH_SIZE", 50)
CHECKPOINT_INTERVAL = _env_int("CRAWL_CHECKPOINT_INTERVAL", 50)
MAX_RETRIES = _env_int("CRAWL_MAX_RETRIES", 3)

# ─────────────── 实盘组合新接口（spzhapi，2026-08 迁移后） ───────────────
# 会话令牌会过期，过期后需在模拟器 APP 中重新抓包获取。
# 令牌请放入本地 .env（已 gitignore），不要提交到仓库。
SPZH_API_URL = os.getenv("SPZH_API_URL", "https://spzhapi.dfcfs.cn/rtV3")
SPZH_CT_TOKEN = os.getenv("SPZH_CT_TOKEN", "")
SPZH_UT_TOKEN = os.getenv("SPZH_UT_TOKEN", "")
SPZH_USER_ID = os.getenv("SPZH_USER_ID", "")
SPZH_DEVICE_ID = os.getenv("SPZH_DEVICE_ID", "")
SPZH_APP_VERSION = os.getenv("SPZH_APP_VERSION", "11.2.2")
SPZH_RN_VERSION = os.getenv("SPZH_RN_VERSION", "2.3.0.260731172423109")

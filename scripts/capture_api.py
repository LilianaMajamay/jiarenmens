"""
mitmproxy 抓包插件：记录东方财富实盘组合相关接口的完整请求/响应。

用法:
    .venv\\Scripts\\mitmdump.exe -s scripts\\capture_api.py -p 8080

输出:
    logs/capture_flows.jsonl  所有命中的请求（JSON Lines）
    logs/capture_ssl.log      握手失败记录（用于判断 APP 是否证书锁定）
"""
import json
import time
from pathlib import Path

from mitmproxy import http

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
FLOW_FILE = LOG_DIR / "capture_flows.jsonl"
SSL_FILE = LOG_DIR / "capture_ssl.log"

# 关注域名：东方财富生态（API / 行情 / 配置，排除静态资源 CDN）
KEY_HOSTS = (
    "eastmoney.com",
    "dfcfs.cn",
    "dfcfs.com",
    "18.cn",
    "dflcs.com.cn",
)


def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def _interesting(url: str) -> bool:
    host = _host_of(url)
    return any(k in host for k in KEY_HOSTS)


def _safe_headers(headers) -> dict:
    out = {}
    for k, v in headers.items():
        # 记录全部请求头（关键域名），避免遗漏 WAF 校验字段
        out[k] = v[:600]
    return out


def _truncate(body: bytes, limit: int = 4000) -> str:
    if not body:
        return ""
    text = body.decode("utf-8", errors="replace")
    return text[:limit] + ("..." if len(text) > limit else "")


def _content(flow_side, limit: int = 4000) -> str:
    """读取请求/响应内容（自动解压 gzip/br），失败则退回原始字节。"""
    try:
        data = flow_side.get_content()
    except Exception:
        data = flow_side.raw_content or b""
    return _truncate(data, limit)


def request(flow: http.HTTPFlow) -> None:
    if _interesting(flow.request.pretty_url):
        rec = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "client": flow.client_conn.peername[0] if flow.client_conn else "",
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "request_headers": _safe_headers(flow.request.headers),
            "request_body": _content(flow.request),
        }
        with FLOW_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def response(flow: http.HTTPFlow) -> None:
    if _interesting(flow.request.pretty_url):
        rec = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "status": flow.response.status_code,
            "client_http_version": getattr(flow.client_conn, "http_version", ""),
            "response_http_version": flow.response.http_version,
            "response_headers": _safe_headers(flow.response.headers),
            "response_body": _content(flow.response),
        }
        with FLOW_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def tls_failed_client(data) -> None:
    # 证书握手失败：通常表示 APP 证书锁定，无法解密
    try:
        addr = data.conn.server_address
    except Exception:
        addr = data
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} TLS握手失败 server={addr}"
    with SSL_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)

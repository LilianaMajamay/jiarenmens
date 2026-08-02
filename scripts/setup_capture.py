"""
抓包环境一键准备脚本

作用：
1. 下载 MuMu 模拟器安装包（Windows 版，从网易官方 API 获取直链）
2. 下载东方财富 APK（从 25pp 历史版本页抓最新版）
3. 下载 frida-server（Android x86_64，版本与已装 frida-tools 匹配）
4. 安装抓包依赖（mitmproxy / frida-tools）

下载产物统一放到项目根目录 tools/ 下。
模拟器安装、root、证书、代理等步骤见 docs/抓包环境搭建.md。
"""
import json
import lzma
import re
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
SESSION = requests.Session()
SESSION.trust_env = False  # 禁用系统代理，避免被本地代理干扰


def download(url: str, dest: Path, referer: str = ""):
    TOOLS.mkdir(parents=True, exist_ok=True)
    print(f"下载: {url[:100]}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    }
    if referer:
        headers["Referer"] = referer
    with SESSION.get(url, headers=headers, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
    size = dest.stat().st_size / 1024 / 1024
    print(f"  -> {dest} ({size:.1f} MB)")


def download_mumu() -> Path:
    """通过网易 API 获取 MuMu Windows 安装包直链（302 跳转）。"""
    resp = SESSION.get(
        "https://mumu.nie.netease.com/api/dl/win?channel=gw_win",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=60,
        allow_redirects=False,
    )
    url = resp.headers.get("Location", "")
    if not url:
        raise RuntimeError("MuMu 下载直链解析失败")
    dest = TOOLS / "mumu_installer.exe"
    download(url, dest, referer="https://mumu.163.com/download/")
    return dest


def download_apk() -> Path:
    """从 25pp 历史版本页抓取东方财富最新 APK 直链。"""
    resp = SESSION.get(
        "https://www.25pp.com/xiazai/39395/history/",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"},
        timeout=60,
    )
    html = resp.text
    links = re.findall(r'https?://android-apps\.25pp\.com[^\s"\']+\.apk[^\s"\']*', html)
    if not links:
        raise RuntimeError("25pp 未找到 APK 链接，请手动下载东方财富 11.2.2 APK")
    dest = TOOLS / "dfcf.apk"
    download(links[0], dest, referer="https://www.25pp.com/")
    return dest


def download_frida_server() -> Path:
    """下载 frida-server（Android x86_64），版本与已装 frida 一致。"""
    try:
        import frida
        ver = frida.__version__
    except ImportError:
        ver = "17.16.4"
    url = f"https://github.com/frida/frida/releases/download/{ver}/frida-server-{ver}-android-x86_64.xz"
    dest = TOOLS / f"frida-server-{ver}-android-x86_64.xz"
    download(url, dest)
    return dest


def install_capture_deps():
    """安装抓包依赖到项目 venv。"""
    print("==> 安装抓包依赖 (mitmproxy/frida-tools)")
    if VENV_PY.exists():
        subprocess.run([str(VENV_PY), "-m", "pip", "install", "-r",
                        str(ROOT / "scripts" / "requirements-capture.txt")], check=False)
    else:
        print("未找到 .venv，请先创建虚拟环境: python -m venv .venv")


if __name__ == "__main__":
    print("===== 东方财富抓包环境准备 =====")
    download_mumu()
    download_apk()
    download_frida_server()
    install_capture_deps()
    print("\n下载完成，产物在 tools/ 目录。")
    print("后续步骤见 docs/抓包环境搭建.md：安装 MuMu → 安装 APK → root → 证书 → 代理 → 抓包")

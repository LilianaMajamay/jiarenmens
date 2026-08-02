"""用 Frida 启动东方财富并注入 SSL Pinning 绕过脚本，保持会话存活。"""
import os
import subprocess
import sys
import time
from pathlib import Path

import frida

PACKAGE = "com.eastmoney.android.berlin"
SCRIPT_PATH = Path(__file__).resolve().parent / "frida_unpin.js"
DEVICE_ID = "127.0.0.1:16384"
ADB = r"D:\AndroidSDK\platform-tools\adb.exe"
ACTIVITY = "com.eastmoney.android.berlin/.activity.MainActivity"


def main():
    dev = frida.get_device_manager().get_device(DEVICE_ID, timeout=10)
    print(f"设备: {dev.id}", flush=True)

    # spawn 模式（反调试 APP 对后附加会自杀，spawn 则安全）
    subprocess.run([ADB, "-s", DEVICE_ID, "shell", "am", "force-stop", PACKAGE],
                   capture_output=True)
    time.sleep(2)
    pid = dev.spawn([PACKAGE])
    print(f"spawn APP, pid={pid}", flush=True)
    session = dev.attach(pid)
    with open(SCRIPT_PATH, encoding="utf-8") as f:
        code = f.read()
    script = session.create_script(code)
    script.on("message", lambda message, data: print(message, flush=True))
    script.load()
    print("脚本已注入", flush=True)
    dev.resume(pid)
    print("APP 已恢复运行，保持会话...", flush=True)
    print("保持会话...", flush=True)

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            session.detach()
        except Exception:
            pass


if __name__ == "__main__":
    main()

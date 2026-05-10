"""
诊断脚本：打开一个选手页面，等待 30 秒，把渲染结果完整 dump 到 data/debug/

用法:
    python3 scripts/diagnose.py
    python3 scripts/diagnose.py 900113132   # 指定 zh_id

输出 (data/debug/):
    info_<zh_id>.html     详情页最终 HTML
    info_<zh_id>.png      详情页全屏截图
    detail_<zh_id>.html   持仓页最终 HTML
    detail_<zh_id>.png    持仓页全屏截图
    change_<zh_id>.html   调仓页最终 HTML
    change_<zh_id>.png    调仓页全屏截图
    console_<zh_id>.log   三个页面合并后的浏览器控制台输出
    network_<zh_id>.log   失败的网络请求列表
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright

from src.config import (
    USER_AGENT,
    PLAYER_INFO_URL,
    POSITION_URL,
    TRADE_URL,
    DATA_DIR,
)
from src.utils.async_playwright_pool import AsyncPlaywrightPool


PAGE_WAIT_SECONDS = 30  # 给 SPA 充分时间渲染


async def dump_page(
    ctx,
    name: str,
    url: str,
    debug_dir: Path,
    console_lines: list,
    failed_reqs: list,
    xhr_log: list,
):
    """打开一个 URL，等渲染，保存 HTML + 截图，记录 console / 失败请求 / XHR & fetch"""
    page = await ctx.new_page()

    page.on(
        "console",
        lambda msg: console_lines.append(f"[{name}][{msg.type}] {msg.text}")
    )
    page.on(
        "pageerror",
        lambda exc: console_lines.append(f"[{name}][pageerror] {exc}")
    )
    page.on(
        "requestfailed",
        lambda req: failed_reqs.append(
            f"[{name}] {req.method} {req.url} -> {req.failure}"
        )
    )

    async def _on_response(resp):
        try:
            req = resp.request
            rtype = req.resource_type
            if rtype not in ("xhr", "fetch"):
                return
            body_preview = ""
            try:
                buf = await resp.body()
                txt = buf.decode('utf-8', errors='replace')
                body_preview = txt[:500].replace('\n', ' ')
            except Exception as e:
                body_preview = f"<read body err: {e}>"
            xhr_log.append(
                f"[{name}] {req.method} {resp.status} {req.url}\n"
                f"    body[0:500]={body_preview}"
            )
        except Exception as e:
            xhr_log.append(f"[{name}] <response handler error: {e}>")

    page.on("response", lambda resp: asyncio.create_task(_on_response(resp)))

    try:
        print(f"  → 打开 {name}: {url}")
        await page.goto(url, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(PAGE_WAIT_SECONDS)

        html = await page.content()
        body_text = await page.evaluate(
            "document.body ? document.body.innerText.slice(0, 500) : '<no body>'"
        )
        bridge_state = await page.evaluate(
            """() => ({
                emh5: typeof window.emh5,
                EMProjJs: typeof window.EMProjJs,
                EMRead: typeof window.EMRead,
                emjs: typeof window.emjs,
            })"""
        )

        (debug_dir / f"{name}_html.html").write_text(html, encoding='utf-8')
        await page.screenshot(path=str(debug_dir / f"{name}_screenshot.png"), full_page=True)

        print(f"    HTML 长度: {len(html)} 字节")
        print(f"    body innerText 前 200 字: {body_text[:200]!r}")
        print(f"    桥接对象: {bridge_state}")
        print(f"    截图已保存")
    except Exception as e:
        print(f"    [错误] {e}")
    finally:
        await page.close()


async def main():
    zh_id = sys.argv[1] if len(sys.argv) > 1 else "900113132"

    debug_dir = DATA_DIR / "debug" / zh_id
    debug_dir.mkdir(parents=True, exist_ok=True)
    print(f"[*] 诊断输出目录: {debug_dir}")

    pool = AsyncPlaywrightPool(pool_size=1)
    await pool.initialize()

    console_lines: list = []
    failed_reqs: list = []
    xhr_log: list = []

    try:
        async with pool.get_context() as ctx:
            # 验证反检测脚本是否生效
            check_page = await ctx.new_page()
            try:
                await check_page.goto("about:blank")
                fp = await check_page.evaluate(
                    """() => ({
                        webdriver: navigator.webdriver,
                        userAgent: navigator.userAgent,
                        plugins: navigator.plugins.length,
                        languages: navigator.languages,
                        chrome: !!window.chrome,
                    })"""
                )
                print(f"[*] 反检测自检: {fp}")
            finally:
                await check_page.close()

            await dump_page(
                ctx, "info",
                f"{PLAYER_INFO_URL}?zh={zh_id}",
                debug_dir, console_lines, failed_reqs, xhr_log,
            )
            await dump_page(
                ctx, "detail",
                f"{POSITION_URL}?zh={zh_id}",
                debug_dir, console_lines, failed_reqs, xhr_log,
            )
            await dump_page(
                ctx, "change",
                f"{TRADE_URL}?zh={zh_id}",
                debug_dir, console_lines, failed_reqs, xhr_log,
            )

        (debug_dir / "console.log").write_text(
            "\n".join(console_lines) if console_lines else "(空)",
            encoding='utf-8',
        )
        (debug_dir / "network_failed.log").write_text(
            "\n".join(failed_reqs) if failed_reqs else "(无失败请求)",
            encoding='utf-8',
        )
        (debug_dir / "xhr.log").write_text(
            "\n\n".join(xhr_log) if xhr_log else "(没有 XHR/fetch 请求)",
            encoding='utf-8',
        )

        print("\n[*] 完成。请把以下文件打包发给我:")
        for p in sorted(debug_dir.iterdir()):
            print(f"    {p.relative_to(DATA_DIR.parent)}  ({p.stat().st_size} 字节)")

        print(f"\n    打包命令: tar czf debug_{zh_id}.tgz -C data/debug {zh_id}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

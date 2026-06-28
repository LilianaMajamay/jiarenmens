"""Test script: intercept dialog and observe API requests"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright

STEALTH_SCRIPT = """
// Block dialog creation by intercepting appendChild/insertBefore
(function() {
    const origAppendChild = Node.prototype.appendChild;
    const origInsertBefore = Node.prototype.insertBefore;
    const origInnerHTML = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');

    // Intercept appendChild to detect and block dialog elements
    Node.prototype.appendChild = function(child) {
        if (child && child.className && (
            String(child.className).includes('confirm') ||
            String(child.className).includes('mask')
        )) {
            console.log('[STEALTH] Blocked dialog element:', child.className);
            return child;
        }
        return origAppendChild.call(this, child);
    };

    Node.prototype.insertBefore = function(child, ref) {
        if (child && child.className && (
            String(child.className).includes('confirm') ||
            String(child.className).includes('mask')
        )) {
            console.log('[STEALTH] Blocked dialog insert:', child.className);
            return child;
        }
        return origInsertBefore.call(this, child, ref);
    };

    // Set emconfig early
    window.emconfig = {
        pkgName: 'app_group_page',
        pkgVersion: '1.0.0',
        buildTime: 1776934691271,
        buildDate: '2026/4/23 16:58:11',
        isBuild: true,
        default: {
            api: {
                yuantao: 'https://emzuhelist.eastmoney.com',
                api001: 'https://emdcspzhapi.dfcfs.cn/',
                api003: 'https://emstockdiag.eastmoney.com/',
                searchApi: 'https://searchapi.eastmoney.com/',
                pushApi: 'https://push2.eastmoney.com'
            }
        }
    };
})();
"""

async def main():
    zh_id = sys.argv[1] if len(sys.argv) > 1 else "900113132"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 414, "height": 896},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)"
            ),
            locale='zh-CN',
        )
        await ctx.add_init_script(STEALTH_SCRIPT)

        page = await ctx.new_page()

        # Track all requests
        api_calls = []

        page.on("request", lambda req: api_calls.append({
            'method': req.method,
            'url': req.url,
            'headers': req.headers,
            'post_data': req.post_data,
        }))

        page.on("response", lambda resp: print(f"  ← {resp.status} {resp.url}"))
        page.on("console", lambda msg: print(f"  [console] {msg.text}"))
        page.on("pageerror", lambda err: print(f"  [error] {err}"))

        url = f"https://groupwap.eastmoney.com/group/reality/info.html?zh={zh_id}"
        print(f"Loading: {url}")

        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(10)  # Wait for SPA to initialize

            print(f"\n=== API calls ({len(api_calls)}) ===")
            for c in api_calls:
                print(f"  {c['method']} {c['url']}")
                if c['post_data']:
                    print(f"    body: {c['post_data']}")

            # Check page state
            body_text = await page.evaluate("document.body ? document.body.innerText.slice(0, 1000) : 'no body'")
            print(f"\n=== Page content (first 500 chars) ===")
            print(body_text[:500])

        except Exception as e:
            print(f"Error: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

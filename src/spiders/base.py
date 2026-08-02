"""
东方财富实盘选手爬虫 - 异步页面获取工具

提供两个独立函数：
- fetch_page_with_playwright()   — 获取静态动态页面
- fetch_page_with_scroll()       — 获取需滚动加载的动态页面
"""
import asyncio
import json as _json
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.utils.logger import setup_logger
from src.utils.async_playwright_pool import AsyncPlaywrightPool
from src.config import MAX_RETRIES

logger = setup_logger()

RETRY_DELAY = 2  # 秒
WAIT_TARGET_TIMEOUT_MS = 15000  # 等待目标渲染的超时（毫秒）


# =============================================================================
# 页面等待工具
# =============================================================================

async def _wait_for_target(page, wait_for_selector: Optional[str], wait_for_text: Optional[str]) -> None:
    """优先等待 CSS 选择器或文本出现；都没有则用短 networkidle 兜底。"""
    try:
        if wait_for_selector:
            await page.wait_for_selector(wait_for_selector, timeout=WAIT_TARGET_TIMEOUT_MS, state='attached')
            return
        if wait_for_text:
            expr = "document.body && document.body.innerText.includes(" + _json.dumps(wait_for_text) + ")"
            await page.wait_for_function(expr, timeout=WAIT_TARGET_TIMEOUT_MS)
            return
        await page.wait_for_load_state('networkidle', timeout=5000)
    except PlaywrightTimeoutError as e:
        target = wait_for_selector or wait_for_text or 'networkidle'
        logger.warning(f"等待 {target!r} 超时，继续解析当前页面: {e}")


# =============================================================================
# 页面获取函数
# =============================================================================

async def fetch_page_with_playwright(
    pool: AsyncPlaywrightPool,
    url: str,
    timeout: int = 60,
    retries: int = MAX_RETRIES,
    wait_for_selector: Optional[str] = None,
    wait_for_text: Optional[str] = None,
) -> Optional[str]:
    """
    使用 Playwright 获取动态页面内容。

    Args:
        pool: Playwright 连接池
        url: 目标 URL
        timeout: 单个请求超时（秒）
        wait_for_selector: 等待指定 CSS 选择器出现
        wait_for_text: 等待页面文本包含该内容
    """
    for attempt in range(retries):
        try:
            async with pool.get_context(timeout) as ctx:
                page = await ctx.new_page()
                try:
                    # 先等 DOM 解析完成，再等网络空闲（JS 加载执行完）
                    await page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
                    try:
                        await page.wait_for_load_state('networkidle', timeout=20000)
                    except Exception:
                        pass  # networkidle 超时不致命，继续
                    await _wait_for_target(page, wait_for_selector, wait_for_text)

                    # 隐藏"前往东方财富APP"确认对话框（服务端渲染在 HTML 中）
                    await page.evaluate(
                        "var e=document.querySelector('.confirm, .mask');if(e)e.style.display='none'"
                    )

                    content = await page.content()

                    # 反爬检查
                    page_lower = content.lower()
                    if any(kw in page_lower for kw in ('验证', 'captcha', 'blocked', 'access denied', '404')):
                        snippet = content[:200].replace('\n', ' ').strip()
                        logger.warning(f"页面可能被拦截 (url={url}, 片段={snippet})")
                        if attempt < retries - 1:
                            continue

                    return content
                finally:
                    await page.close()

        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"Playwright 获取失败 (尝试 {attempt+1}/{retries}): {e}")
                await asyncio.sleep(RETRY_DELAY)
            else:
                logger.error(f"Playwright 获取失败 {url}: {e}")
                return None

    return None


async def fetch_page_with_scroll(
    pool: AsyncPlaywrightPool,
    url: str,
    timeout: int = 60,
    scroll_pause: float = 1.0,
    max_scrolls: int = 20,
    retries: int = MAX_RETRIES,
    wait_for_selector: Optional[str] = None,
    wait_for_text: Optional[str] = None,
) -> Optional[str]:
    """获取页面内容并模拟滚动加载（参数同上）。"""
    for attempt in range(retries):
        try:
            async with pool.get_context(timeout) as ctx:
                page = await ctx.new_page()
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
                    try:
                        await page.wait_for_load_state('networkidle', timeout=20000)
                    except Exception:
                        pass
                    await _wait_for_target(page, wait_for_selector, wait_for_text)

                    # 隐藏"前往东方财富APP"确认对话框
                    await page.evaluate(
                        "var e=document.querySelector('.confirm, .mask');if(e)e.style.display='none'"
                    )

                    for _ in range(max_scrolls):
                        await page.evaluate("window.scrollBy(0, 500)")
                        await asyncio.sleep(scroll_pause)

                        try:
                            load_more = page.locator('text=加载更多').first
                            if await load_more.is_visible():
                                await load_more.click()
                                await asyncio.sleep(scroll_pause)
                        except Exception:
                            pass

                    return await page.content()
                finally:
                    await page.close()

        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"滚动获取失败 (尝试 {attempt+1}/{retries}): {e}")
                await asyncio.sleep(RETRY_DELAY)
            else:
                logger.error(f"滚动获取失败 {url}: {e}")
                return None

    return None


# =============================================================================
# 向下兼容：旧 AsyncBaseSpider 类（不再使用，保留引用避免导入报错）
# =============================================================================

class AsyncBaseSpider:
    """
    旧式爬虫基类（已废弃，请直接使用 fetch_page_with_playwright / fetch_page_with_scroll）。

    保留以兼容外部导入代码，新版代码不应再使用。
    """
    def __init__(self, pool: AsyncPlaywrightPool = None, pool_size: int = 5):
        self._own_pool = pool is None
        self.pool = pool or AsyncPlaywrightPool(pool_size=pool_size)
        self._pool_initialized = pool is not None

    async def _ensure_pool(self):
        if not self._pool_initialized:
            await self.pool.initialize()
            self._pool_initialized = True

    async def fetch_page_with_playwright(self, *args, **kwargs):
        await self._ensure_pool()
        return await fetch_page_with_playwright(self.pool, *args, **kwargs)

    async def fetch_page_with_scroll(self, *args, **kwargs):
        await self._ensure_pool()
        return await fetch_page_with_scroll(self.pool, *args, **kwargs)

    def parse_html(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, 'lxml')

    async def close(self):
        if self._own_pool and self._pool_initialized:
            await self.pool.close()

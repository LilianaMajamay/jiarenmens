"""
东方财富实盘选手爬虫 - 异步基础爬虫类
"""
import asyncio
import json as _json
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.utils.logger import setup_logger
from src.utils.async_playwright_pool import AsyncPlaywrightPool

logger = setup_logger()

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒

# 等待目标渲染的超时（毫秒）
WAIT_TARGET_TIMEOUT_MS = 15000


async def _wait_for_target(
    page,
    wait_for_selector: Optional[str],
    wait_for_text: Optional[str],
) -> None:
    """优先等待具体选择器/文本出现；都没指定则用较短的 networkidle 兜底。

    任何等待失败只记录警告并继续返回当前页面，避免整体失败。
    """
    try:
        if wait_for_selector:
            await page.wait_for_selector(
                wait_for_selector,
                timeout=WAIT_TARGET_TIMEOUT_MS,
                state='attached',
            )
            return
        if wait_for_text:
            expr = (
                "document.body && document.body.innerText.includes("
                + _json.dumps(wait_for_text)
                + ")"
            )
            await page.wait_for_function(expr, timeout=WAIT_TARGET_TIMEOUT_MS)
            return
        # 兜底：等到没有进行中的网络请求；超时不致命
        await page.wait_for_load_state('networkidle', timeout=5000)
    except PlaywrightTimeoutError as e:
        target = wait_for_selector or wait_for_text or 'networkidle'
        logger.warning(f"等待 {target!r} 超时，继续解析当前页面: {e}")


class AsyncBaseSpider:
    """异步基础爬虫类"""

    def __init__(self, pool: AsyncPlaywrightPool = None, pool_size: int = 5):
        if pool is None:
            self._own_pool = True
            self.pool = AsyncPlaywrightPool(pool_size=pool_size)
            self._pool_initialized = False
        else:
            self._own_pool = False
            self.pool = pool
            # 复用外部 pool 时假定其已初始化（由调用方保证）
            self._pool_initialized = True

    async def _ensure_pool(self):
        """确保池已初始化"""
        if not self._pool_initialized:
            await self.pool.initialize()
            self._pool_initialized = True

    async def fetch_page_with_playwright(
        self,
        url: str,
        timeout: int = 60,
        retries: int = MAX_RETRIES,
        wait_for_selector: Optional[str] = None,
        wait_for_text: Optional[str] = None,
    ) -> Optional[str]:
        """使用异步 Playwright 获取动态页面

        Args:
            wait_for_selector: 等待具体 CSS 选择器出现（最优）
            wait_for_text: 等待 body innerText 包含某文本（次选）
            两者都未指定时使用 networkidle 兜底
        """
        await self._ensure_pool()

        for attempt in range(retries):
            try:
                async with self.pool.get_context(timeout) as ctx:
                    page = await ctx.new_page()
                    try:
                        await page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
                        await _wait_for_target(page, wait_for_selector, wait_for_text)

                        content = await page.content()

                        # 检查页面是否被反爬拦截（打印前200字符用于诊断）
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
                    logger.warning(f"异步 Playwright 获取失败 (尝试 {attempt+1}/{retries}): {e}")
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    logger.error(f"异步 Playwright 获取失败: {e}")
                    return None

        return None

    async def fetch_page_with_scroll(
        self,
        url: str,
        timeout: int = 60,
        scroll_pause: float = 1.0,
        max_scrolls: int = 20,
        retries: int = MAX_RETRIES,
        wait_for_selector: Optional[str] = None,
        wait_for_text: Optional[str] = None,
    ) -> Optional[str]:
        """使用异步 Playwright 获取动态页面并滚动加载（参数同上）"""
        await self._ensure_pool()

        for attempt in range(retries):
            try:
                async with self.pool.get_context(timeout) as ctx:
                    page = await ctx.new_page()
                    try:
                        await page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
                        await _wait_for_target(page, wait_for_selector, wait_for_text)

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
                    logger.warning(f"异步滚动获取失败 (尝试 {attempt+1}/{retries}): {e}")
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    logger.error(f"异步滚动获取失败: {e}")
                    return None

        return None

    def parse_html(self, html: str) -> BeautifulSoup:
        """解析HTML"""
        return BeautifulSoup(html, 'lxml')

    async def close(self):
        """关闭资源"""
        if self._own_pool and self._pool_initialized:
            await self.pool.close()

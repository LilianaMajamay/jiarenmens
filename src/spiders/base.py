"""
东方财富实盘选手爬虫 - 异步基础爬虫类
"""
import asyncio
import aiohttp
from typing import Optional

from bs4 import BeautifulSoup

from src.config import HEADERS
from src.utils.logger import setup_logger
from src.utils.async_playwright_pool import AsyncPlaywrightPool

logger = setup_logger()

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒


class AsyncBaseSpider:
    """异步基础爬虫类"""

    def __init__(self, pool: AsyncPlaywrightPool = None, pool_size: int = 5):
        if pool is None:
            self._own_pool = True
            self.pool = AsyncPlaywrightPool(pool_size=pool_size)
        else:
            self._own_pool = False
            self.pool = pool

        self._pool_initialized = False
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_pool(self):
        """确保池已初始化"""
        if not self._pool_initialized:
            await self.pool.initialize()
            self._pool_initialized = True

    async def _ensure_session(self):
        """确保 aiohttp session 已创建（复用连接）"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=HEADERS)

    async def fetch_page(self, url: str, timeout: int = 30) -> Optional[str]:
        """使用 aiohttp 获取页面（复用 session）"""
        try:
            await self._ensure_session()
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                response.raise_for_status()
                return await response.text()
        except Exception as e:
            logger.warning(f"aiohttp 获取失败: {e}")
            return None

    async def fetch_page_with_playwright(
        self,
        url: str,
        timeout: int = 60,
        retries: int = MAX_RETRIES
    ) -> Optional[str]:
        """使用异步 Playwright 获取动态页面"""
        await self._ensure_pool()

        for attempt in range(retries):
            try:
                async with self.pool.get_context(timeout) as ctx:
                    page = await ctx.new_page()
                    try:
                        await page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
                        await page.wait_for_timeout(3000)
                        return await page.content()
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
        scroll_pause: float = 0.5,
        max_scrolls: int = 20,
        retries: int = MAX_RETRIES
    ) -> Optional[str]:
        """使用异步 Playwright 获取动态页面并滚动加载"""
        await self._ensure_pool()

        for attempt in range(retries):
            try:
                async with self.pool.get_context(timeout) as ctx:
                    page = await ctx.new_page()
                    try:
                        await page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
                        await page.wait_for_timeout(3000)

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
        if self._session and not self._session.closed:
            await self._session.close()

        if self._own_pool and self._pool_initialized:
            await self.pool.close()

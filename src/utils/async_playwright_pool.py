"""
异步 Playwright 连接池

核心设计：
- 单个 Playwright + Browser 实例（启动一次）
- 多个 BrowserContext 组成连接池
- 每个 context 可复用，避免频繁创建/销毁
- 使用 Semaphore 控制并发，无需额外锁
"""
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, Generator

from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page

from src.utils.logger import setup_logger

logger = setup_logger()


class AsyncPlaywrightPool:
    """
    异步 Playwright Context 连接池

    生命周期：
    1. initialize() - 启动 Playwright 和 Browser，创建 Context 池
    2. acquire() - 从池中获取一个可用的 Context
    3. release() - 将 Context 返回池中（如果有效）
    4. close() - 关闭所有资源

    使用示例：
        pool = AsyncPlaywrightPool(pool_size=5)
        await pool.initialize()

        async with pool.get_context() as ctx:
            page = await ctx.new_page()
            await page.goto(url)
            content = await page.content()

        await pool.close()
    """

    def __init__(
        self,
        pool_size: int = 5,
        headless: bool = True
    ):
        """
        初始化连接池

        Args:
            pool_size: Context 池大小，默认 5
            headless: 是否无头模式，默认 True
        """
        self.pool_size = pool_size
        self.headless = headless

        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None

        self._context_pool: asyncio.Queue[BrowserContext] = None
        self._used_contexts: set[BrowserContext] = set()
        self._semaphore: asyncio.Semaphore = None

        self._initialized = False

    async def initialize(self):
        """初始化 Playwright 和 Browser，创建 Context 池"""
        if self._initialized:
            logger.warning("Pool already initialized")
            return

        logger.info(f"初始化 AsyncPlaywrightPool (pool_size={self.pool_size})...")

        # 启动 Playwright
        self.playwright = await async_playwright().start()
        logger.debug("Playwright 启动成功")

        # 启动 Chromium
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless
        )
        logger.debug("Chromium 浏览器启动成功")

        # 创建 Context 池
        self._context_pool = asyncio.Queue()
        for i in range(self.pool_size):
            ctx = await self.browser.new_context()
            await self._context_pool.put(ctx)
            logger.debug(f"Context {i+1}/{self.pool_size} 创建成功")

        # 使用 Semaphore 控制并发（替代 Lock）
        self._semaphore = asyncio.Semaphore(self.pool_size)

        self._initialized = True
        logger.info(f"AsyncPlaywrightPool 初始化完成 (pool_size={self.pool_size})")

    async def acquire(self, timeout: float = 60) -> BrowserContext:
        """
        从池中获取一个可用的 Context

        Args:
            timeout: 超时时间（秒）

        Returns:
            BrowserContext: 可用的浏览器上下文
        """
        if not self._initialized:
            raise RuntimeError("Pool not initialized. Call initialize() first.")

        # 使用 semaphore 限流，不需要额外锁
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"获取 Context 超时 ({timeout}s)，池已满")

        try:
            ctx = await asyncio.wait_for(
                self._context_pool.get(),
                timeout=timeout
            )
            self._used_contexts.add(ctx)
            return ctx
        except asyncio.TimeoutError:
            self._semaphore.release()
            raise TimeoutError(f"获取 Context 超时 ({timeout}s)，池已满")

    async def release(self, ctx: BrowserContext):
        """
        将 Context 返回池中

        如果 Context 已失效（浏览器断开），则创建一个新的替换

        Args:
            ctx: 要释放的 Context
        """
        if ctx not in self._used_contexts:
            self._semaphore.release()
            return

        self._used_contexts.remove(ctx)

        # 检查 Context 是否还有效
        try:
            # 尝试访问 pages 属性来判断是否断开
            if ctx.pages:
                await self._context_pool.put(ctx)
                logger.debug("Context 释放回池")
                self._semaphore.release()
                return
        except Exception as e:
            logger.warning(f"Context 已失效: {e}")

        # Context 无效，创建新的替换
        try:
            new_ctx = await self.browser.new_context()
            await self._context_pool.put(new_ctx)
            logger.debug("Context 已替换")
        except Exception as e:
            logger.error(f"创建新 Context 失败: {e}")

        self._semaphore.release()

    @asynccontextmanager
    async def get_context(self, timeout: float = 60) -> Generator[BrowserContext, None, None]:
        """
        获取 Context 的上下文管理器

        Usage:
            async with pool.get_context() as ctx:
                page = await ctx.new_page()
                await page.goto(url)
        """
        ctx = await self.acquire(timeout)
        try:
            yield ctx
        finally:
            await self.release(ctx)

    async def fetch_page(self, url: str, timeout: int = 60) -> Optional[str]:
        """
        快捷方法：直接获取页面内容

        Args:
            url: 页面 URL
            timeout: 超时时间（秒）

        Returns:
            页面 HTML 内容，或 None
        """
        async with self.get_context(timeout) as ctx:
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
                await page.wait_for_timeout(3000)
                return await page.content()
            except Exception as e:
                logger.error(f"获取页面失败 {url}: {e}")
                return None
            finally:
                await page.close()

    async def fetch_page_with_scroll(
        self,
        url: str,
        timeout: int = 60,
        scroll_pause: float = 0.5,
        max_scrolls: int = 20
    ) -> Optional[str]:
        """
        快捷方法：获取页面内容并滚动加载

        Args:
            url: 页面 URL
            timeout: 超时时间（秒）
            scroll_pause: 每次滚动后等待时间
            max_scrolls: 最大滚动次数

        Returns:
            页面 HTML 内容，或 None
        """
        async with self.get_context(timeout) as ctx:
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)

                # 等待初始内容加载
                await page.wait_for_timeout(3000)
                for i in range(max_scrolls):
                    await page.evaluate("window.scrollBy(0, 500)")
                    await asyncio.sleep(scroll_pause)

                    # 尝试点击"加载更多"按钮
                    try:
                        load_more = page.locator('text=加载更多').first
                        if await load_more.is_visible():
                            await load_more.click()
                            await asyncio.sleep(scroll_pause)
                    except Exception:
                        pass

                return await page.content()
            except Exception as e:
                logger.error(f"获取滚动页面失败 {url}: {e}")
                return None
            finally:
                await page.close()

    async def close(self):
        """关闭所有资源"""
        logger.info("关闭 AsyncPlaywrightPool...")

        # 关闭池中所有 contexts
        if self._context_pool:
            while not self._context_pool.empty():
                try:
                    ctx = self._context_pool.get_nowait()
                    await ctx.close()
                except asyncio.QueueEmpty:
                    break

        # 关闭正在使用的 contexts
        for ctx in list(self._used_contexts):
            try:
                await ctx.close()
            except Exception as e:
                logger.warning(f"关闭使用中的 Context 时出错: {e}")
        self._used_contexts.clear()

        # 关闭浏览器
        if self.browser:
            try:
                await self.browser.close()
                logger.debug("Browser 已关闭")
            except Exception as e:
                logger.warning(f"关闭 Browser 时出错: {e}")

        # 停止 Playwright
        if self.playwright:
            try:
                await self.playwright.stop()
                logger.debug("Playwright 已停止")
            except Exception as e:
                logger.warning(f"停止 Playwright 时出错: {e}")

        self._initialized = False
        logger.info("AsyncPlaywrightPool 已关闭")

    def __repr__(self):
        return f"AsyncPlaywrightPool(pool_size={self.pool_size}, initialized={self._initialized})"


# 全局连接池实例
_pool: Optional[AsyncPlaywrightPool] = None


def get_async_pool(pool_size: int = 5, force_new: bool = False) -> AsyncPlaywrightPool:
    """
    获取全局异步连接池（单例模式）

    Args:
        pool_size: Context 池大小
        force_new: 是否强制创建新实例

    Returns:
        AsyncPlaywrightPool 实例
    """
    global _pool

    if force_new:
        return AsyncPlaywrightPool(pool_size=pool_size)

    if _pool is None:
        _pool = AsyncPlaywrightPool(pool_size=pool_size)

    return _pool


async def close_async_pool():
    """关闭全局连接池"""
    global _pool

    if _pool:
        await _pool.close()
        _pool = None


# 测试代码
if __name__ == "__main__":
    async def test_pool():
        pool = AsyncPlaywrightPool(pool_size=3)
        await pool.initialize()
        print(f"Pool: {pool}")

        # 测试获取多个 contexts
        for i in range(3):
            ctx = await pool.acquire()
            print(f"Acquired context {i+1}: {ctx}")

        # 测试释放
        for i in range(3):
            ctx = await pool.acquire()
            print(f"Releasing context {i+1}")
            await pool.release(ctx)

        # 测试上下文管理器
        async with pool.get_context() as ctx:
            page = await ctx.new_page()
            await page.goto("https://example.com")
            print(f"Page title: {await page.title()}")
            await page.close()

        await pool.close()
        print("Test passed!")

    asyncio.run(test_pool())
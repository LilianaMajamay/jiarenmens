import re
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
from src.spiders.base import AsyncBaseSpider
from src.config import PLAYER_INFO_URL
from src.utils.logger import setup_logger

logger = setup_logger()


def parse_player_detail(soup: BeautifulSoup, zh_id: str) -> Dict[str, Any]:
    """解析选手详情（通用函数）"""
    player = {'zh_id': zh_id}

    # 获取所有文本内容进行匹配
    page_text = soup.get_text()
    page_text = re.sub(r'\s+', ' ', page_text)

    # 获取选手名称
    name_match = re.search(r'([^\s]{2,10})实盘', page_text)
    if not name_match:
        name_match = re.search(r'管理人[：:]\s*([^\s]+)', page_text)
    player['name'] = name_match.group(1).strip() if name_match else ''

    # 提取关注人数 - 格式: "5人关注"
    followers_match = re.search(r'(\d+)\s*人关注', page_text)
    player['followers'] = int(followers_match.group(1)) if followers_match else 0

    # 提取总收益率 - 格式: "总收益 5人关注 -27.23 %"
    total_return_match = re.search(r'总收益\s*(\d+人关注\s*)?(-?\d+\.\d+)\s*%', page_text)
    player['total_return'] = float(total_return_match.group(2)) if total_return_match else 0.0

    # 提取日收益率 - 格式: "日收益 22.21%"
    daily_return_match = re.search(r'日收益\s*([-\d.]+)%', page_text)
    if not daily_return_match:
        daily_return_match = re.search(r'日收益\s*([-\d.]+)', page_text)
    player['daily_return'] = float(daily_return_match.group(1)) if daily_return_match else 0.0

    # 提取净值 - 格式: "已运行 0.728 50.44%"
    net_value_match = re.search(r'已运行\s*([\d.]+)', page_text)
    player['net_value'] = float(net_value_match.group(1)) if net_value_match else 0.0

    # 提取最大回撤 - 格式: "50.44%"
    max_drawdown_match = re.search(r'已运行\s*[\d.]+\s*([-\d.]+)%', page_text)
    player['max_drawdown'] = float(max_drawdown_match.group(1)) if max_drawdown_match else 0.0

    # 提取胜率 - 格式: "45.83%"
    win_rate_match = re.search(r'已运行\s*[\d.]+\s*[\d.]+%\s*([-\d.]+)%', page_text)
    player['win_rate'] = float(win_rate_match.group(1)) if win_rate_match else 0.0

    # 提取运行天数 - 格式: "138天"
    days_match = re.search(r'(\d+)\s*天', page_text)
    player['days'] = int(days_match.group(1)) if days_match else 0

    # 提取概念标签
    concept_match = re.search(r'(光伏概念|新能源|医药|科技|消费|金融|军工|芯片|人工智能|新能源汽车)', page_text)
    player['concept'] = concept_match.group(1) if concept_match else ''

    # 提取简介
    intro_elem = soup.find(class_=lambda x: x and 'intro' in x if x else False)
    player['intro'] = intro_elem.get_text(strip=True) if intro_elem else ''

    return player


class AsyncPlayerDetailSpider(AsyncBaseSpider):
    """选手详情爬虫（异步版本）"""

    async def fetch_player_detail(self, zh_id: str) -> Optional[Dict[str, Any]]:
        """获取选手详情"""
        url = f"{PLAYER_INFO_URL}?zh={zh_id}"
        logger.debug(f"[异步] 获取选手详情: {zh_id}")

        html = await self.fetch_page_with_playwright(url, timeout=60)
        if not html:
            logger.error(f"[异步] 获取选手 {zh_id} 详情失败")
            return None

        soup = self.parse_html(html)
        player = parse_player_detail(soup, zh_id)
        return player


async def crawl_player_detail_async(zh_id: str, pool=None) -> Optional[Dict[str, Any]]:
    """爬取选手详情（异步入口）"""
    spider = AsyncPlayerDetailSpider(pool=pool)
    try:
        return await spider.fetch_player_detail(zh_id)
    finally:
        await spider.close()


if __name__ == "__main__":
    import asyncio
    detail = asyncio.run(crawl_player_detail_async("900304915"))
    print(detail)
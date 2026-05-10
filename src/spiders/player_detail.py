import re
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
from src.spiders.base import AsyncBaseSpider
from src.config import PLAYER_INFO_URL
from src.utils.logger import setup_logger

logger = setup_logger()

PARSED_FIELDS = {
    'name': '选手名称',
    'followers': '关注人数',
    'total_return': '总收益率',
    'daily_return': '日收益率',
    'net_value': '净值',
    'max_drawdown': '最大回撤',
    'win_rate': '胜率',
    'days': '运行天数',
}


def safe_extract_float(pattern: str, text: str, field_name: str, default: float = 0.0) -> float:
    """安全提取浮点数，提取失败时记录警告"""
    match = re.search(pattern, text)
    if not match:
        logger.warning(f"未能从页面提取 {field_name} (pattern: {pattern})")
        return default
    try:
        return float(match.group(1))
    except (ValueError, IndexError) as e:
        logger.warning(f"解析 {field_name} 失败: {e}")
        return default


def safe_extract_int(pattern: str, text: str, field_name: str, default: int = 0) -> int:
    """安全提取整数，提取失败时记录警告"""
    match = re.search(pattern, text)
    if not match:
        logger.warning(f"未能从页面提取 {field_name} (pattern: {pattern})")
        return default
    try:
        return int(match.group(1))
    except (ValueError, IndexError) as e:
        logger.warning(f"解析 {field_name} 失败: {e}")
        return default


def parse_player_detail(soup: BeautifulSoup, zh_id: str) -> Dict[str, Any]:
    """解析选手详情（通用函数）"""
    player = {'zh_id': zh_id}

    page_text = soup.get_text()
    page_text = re.sub(r'\s+', ' ', page_text)

    # 获取选手名称
    name_match = re.search(r'([^\s]{2,10})实盘', page_text)
    if not name_match:
        name_match = re.search(r'管理人[：:]\s*([^\s]+)', page_text)
    player['name'] = name_match.group(1).strip() if name_match else ''

    # 使用安全提取函数
    player['followers'] = safe_extract_int(r'(\d+)\s*人关注', page_text, 'followers')

    # 总收益率 - 格式: "总收益 5人关注 -27.23 %"
    player['total_return'] = safe_extract_float(
        r'总收益\s*(?:\d+人关注\s*)?(-?\d+\.\d+)\s*%', page_text, 'total_return')

    # 日收益率 - 格式: "日收益 22.21%"
    player['daily_return'] = safe_extract_float(
        r'日收益\s*([-\d.]+)%', page_text, 'daily_return')

    # 净值 - 格式: "已运行 0.728"
    player['net_value'] = safe_extract_float(
        r'已运行\s*([\d.]+)', page_text, 'net_value')

    # 最大回撤 - 格式: "已运行 0.728 50.44%"
    player['max_drawdown'] = safe_extract_float(
        r'已运行\s*[\d.]+\s*([-\d.]+)%', page_text, 'max_drawdown')

    # 胜率 - 格式: "已运行 0.728 50.44% 45.83%"
    player['win_rate'] = safe_extract_float(
        r'已运行\s*[\d.]+\s*[\d.]+%\s*([-\d.]+)%', page_text, 'win_rate')

    # 运行天数 - 格式: "138天"
    player['days'] = safe_extract_int(r'(\d+)\s*天', page_text, 'days')

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

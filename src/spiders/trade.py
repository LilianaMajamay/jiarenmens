import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from src.spiders.base import AsyncBaseSpider
from src.config import TRADE_URL
from src.utils.logger import setup_logger

logger = setup_logger()


def parse_position_ratio(position_str: str) -> float:
    """解析仓位字符串为数值（按匹配长度降序，避免子串误匹配）"""
    if not position_str:
        return 0.0

    position_map = {
        "满仓": 100,
        "9成以上": 95,
        "9成": 90,
        "8成": 80,
        "7成": 70,
        "6成": 60,
        "5成": 50,
        "4成": 40,
        "3成": 30,
        "2成": 20,
        "1成以下": 5,
        "1成": 10,
        "空仓": 0,
    }

    # 按 key 长度降序匹配，避免 "1成" 误匹配 "1成以下"
    for key in sorted(position_map.keys(), key=len, reverse=True):
        if key in position_str:
            return position_map[key]

    match = re.search(r'(\d+)', position_str)
    if match:
        return float(match.group(1))

    return 0.0


def infer_trade_direction(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """根据仓位变化推断买入/卖出方向（会修改传入的 dict）"""
    if not trades or len(trades) <= 1:
        for trade in trades:
            trade["direction"] = "调仓"
            trade["position_change"] = 0
        return trades

    sorted_trades = sorted(trades, key=lambda x: x.get("trade_date", ""), reverse=True)

    stock_history: Dict[str, list] = {}

    for trade in sorted_trades:
        stock_code = trade.get("stock_code", "")
        current_position = parse_position_ratio(trade.get("position_ratio", ""))

        if stock_code not in stock_history:
            stock_history[stock_code] = []
            trade["direction"] = "调仓"
            trade["position_change"] = 0
        else:
            prev_position = stock_history[stock_code][-1]
            change = current_position - prev_position

            if change > 0:
                trade["direction"] = "买入"
            elif change < 0:
                trade["direction"] = "卖出"
            else:
                trade["direction"] = "持有"
            trade["position_change"] = change

        stock_history[stock_code].append(current_position)

    return sorted_trades


def parse_trades(soup: BeautifulSoup, zh_id: str) -> List[Dict[str, Any]]:
    """解析调仓记录（通用函数）"""
    trades = []
    page_text = soup.get_text()
    page_text = re.sub(r'\s+', ' ', page_text)

    # 匹配调仓记录格式: "2026-03-20 上能电气 300827 1笔 9成以上 44.000元"
    pattern = r'(\d{4}-\d{2}-\d{2})\s*([^\s\d]{2,10})\s*(\d{6})\s*(\d+)笔\s*(\S+)\s*([\d.]+)元'
    matches = re.findall(pattern, page_text)

    for match in matches:
        try:
            trade = {
                'zh_id': zh_id,
                'trade_date': match[0],
                'stock_name': match[1],
                'stock_code': match[2],
                'trades': int(match[3]),
                'position_ratio': match[4],
                'position_value': float(match[5]),
                'direction': '',
                'position_change': 0,
            }
            trades.append(trade)
        except (ValueError, IndexError) as e:
            logger.warning(f"解析调仓记录失败: {e}")
            continue

    return trades


class AsyncTradeSpider(AsyncBaseSpider):
    """调仓记录爬虫（异步版本）"""

    async def fetch_trades(self, zh_id: str, uid: str = "") -> List[Dict[str, Any]]:
        """获取调仓记录"""
        url = f"{TRADE_URL}?zh={zh_id}&uid={uid}"
        logger.debug(f"[异步] 获取选手调仓记录: {zh_id}")

        html = await self.fetch_page_with_scroll(url, timeout=60, scroll_pause=0.5, max_scrolls=20)
        if not html:
            logger.error(f"[异步] 获取选手 {zh_id} 调仓记录失败")
            return []

        soup = self.parse_html(html)
        trades = parse_trades(soup, zh_id)
        trades = infer_trade_direction(trades)
        return trades


async def crawl_trades_async(zh_id: str, uid: str = "", pool=None) -> List[Dict[str, Any]]:
    """爬取调仓记录（异步入口）"""
    spider = AsyncTradeSpider(pool=pool)
    try:
        return await spider.fetch_trades(zh_id, uid)
    finally:
        await spider.close()


if __name__ == "__main__":
    import asyncio
    trades = asyncio.run(crawl_trades_async("900304915", ""))
    print(f"获取到 {len(trades)} 条调仓记录")
    for t in trades[:5]:
        print(t)

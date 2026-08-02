"""
持仓数据 — 直接调用新接口 CombinationHoldPositionPermitHandler（替代原 Playwright 抓页面）

用法:
    positions = crawl_positions(zh_id)
"""
from typing import Any, Dict, List

from src.api import spzh_client
from src.utils.logger import setup_logger

logger = setup_logger()


def crawl_positions(zh_id: Any) -> List[Dict[str, Any]]:
    """
    获取单个选手持仓明细。

    注意：需要关注该选手，且选手已授权公开持仓，否则返回空列表。
    """
    return spzh_client.fetch_positions(zh_id)

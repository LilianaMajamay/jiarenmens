"""
调仓记录 — 直接调用新接口 CombinationRelocatePositionHandler（替代原 Playwright 滚动抓取）

用法:
    trades = crawl_trades(zh_id)
"""
from typing import Any, Dict, List

from src.api import spzh_client
from src.utils.logger import setup_logger

logger = setup_logger()


def crawl_trades(zh_id: Any) -> List[Dict[str, Any]]:
    """
    获取单个选手调仓记录。

    注意：需要关注该选手，且选手已授权公开调仓记录，否则返回空列表。
    """
    return spzh_client.fetch_trades(zh_id)

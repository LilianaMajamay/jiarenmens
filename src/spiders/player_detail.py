"""
选手详情 — 直接调用新接口 spzhapi.dfcfs.cn（替代原 Playwright 抓页面）

用法:
    detail = crawl_player_detail(zh_id)
"""
from typing import Any, Dict, Optional

from src.api import spzh_client
from src.utils.logger import setup_logger

logger = setup_logger()


def crawl_player_detail(zh_id: Any, list_info: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    获取单个选手详情。

    Args:
        zh_id: 组合 ID
        list_info: 榜单列表项（可选，用于补充 labels / user_id 等字段）

    Returns:
        选手详情字典，失败返回 None
    """
    detail = spzh_client.fetch_player_detail(zh_id)
    if detail is None:
        return None

    # 用榜单信息补充
    if list_info:
        if not detail.get("name"):
            detail["name"] = list_info.get("name", "")
        if not detail.get("user_id"):
            detail["user_id"] = list_info.get("user_id", "")
        if list_info.get("labels"):
            detail["labels"] = list_info["labels"]
        if list_info.get("ranks"):
            detail["ranks"] = list_info["ranks"]
    return detail

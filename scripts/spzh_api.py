"""
东方财富实盘组合新接口客户端（独立工具，实际实现在 src/api/spzh_client.py）
"""
from src.api.spzh_client import (  # noqa: F401
    call,
    auth_args,
    compute_sign,
    build_envelope,
    deep_sort,
    follow_player,
    fetch_player_detail,
    fetch_positions,
    fetch_trades,
)


def get_rank(page=1, page_size=20, unit="250d", board_type="totalRank"):
    """榜单（新接口 profit_rank_handler）。"""
    return call("profit_rank_handler", {
        "ctToken": "", "utToken": "", "userId": "",
        "pageNum": page, "pageSize": page_size,
        "type": "rate", "unit": unit,
        "drawdownFilterType": "0.2", "assetFilterType": "0k",
        "showOperFlag": False,
    })


def get_detail(combination_id):
    return call("CombinationInfoHandler", auth_args({"combinationId": combination_id}))


def get_yield_summary(combination_id):
    return call("combination_yield_detail_handler", auth_args({"combinationId": combination_id}))


def get_positions_trades(combination_id, page=1, page_size=10, is_last_day=True):
    return call("CombinationRelocatePositionHandler", auth_args({
        "combinationId": combination_id,
        "pageNum": page, "pageSize": page_size, "isLastDay": is_last_day,
    }))


def get_hold_permit(combination_id):
    return call("CombinationHoldPositionPermitHandler", auth_args({"combinationId": combination_id}))


def get_follow_list():
    return call("FollowCombinationQueryHandler", auth_args())


if __name__ == "__main__":
    import json
    print("榜单:", json.dumps(get_rank(1, 2), ensure_ascii=False)[:200])
    print("详情:", json.dumps(get_detail(900209545), ensure_ascii=False)[:200])
    print("收益:", json.dumps(get_yield_summary(900209545), ensure_ascii=False)[:200])
    print("持仓/调仓:", json.dumps(get_positions_trades(900209545), ensure_ascii=False)[:200])
    print("关注列表:", json.dumps(get_follow_list(), ensure_ascii=False)[:200])

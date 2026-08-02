"""
东方财富实盘组合新接口客户端（spzhapi.dfcfs.cn）

接口格式与签名算法来源：模拟器抓包 + RN bundle（LivePortfolio）逆向。
签名: sign = SHA256( SM4-CBC( lowercase(JSON(deepSort(envelope))), key/iv ) .hex )
SM4 密钥/IV 硬编码于 bundle: e4dd41fd138867c3665492702fe277eb
"""
import hashlib
import json
import logging
import random
import string
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from gmssl.sm4 import CryptSM4, SM4_ENCRYPT

from src.config import (
    SPZH_API_URL,
    SPZH_CT_TOKEN,
    SPZH_UT_TOKEN,
    SPZH_USER_ID,
    SPZH_DEVICE_ID,
    SPZH_APP_VERSION,
    SPZH_RN_VERSION,
)

logger = logging.getLogger("dfcfshipan")

SM4_KEY = bytes.fromhex("e4dd41fd138867c3665492702fe277eb")


def deep_sort(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: deep_sort(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [deep_sort(x) for x in obj]
    return obj


def compute_sign(envelope: Dict[str, Any]) -> str:
    """计算 rtV3 请求头 sign。"""
    plain = json.dumps(deep_sort(envelope), separators=(",", ":"), ensure_ascii=False).lower()
    sm4 = CryptSM4()
    sm4.set_key(SM4_KEY, SM4_ENCRYPT)
    ct = sm4.crypt_cbc(SM4_KEY, plain.encode())
    return hashlib.sha256(ct.hex().encode()).hexdigest()


def build_envelope(method: str, args: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now()
    return {
        "args": args,
        "method": method,
        "client": "android",
        "randomCode": now.strftime("%H%M%S") + str(random.randint(0, 999)).zfill(3)
        + "".join(random.choices(string.ascii_letters + string.digits, k=20)),
        "timestamp": int(time.time() * 1000),
        "deviceId": SPZH_DEVICE_ID,
        "clientType": "cfw",
        "clientVersion": SPZH_APP_VERSION,
    }


def call(method: str, args: Dict[str, Any], timeout: int = 20) -> Dict[str, Any]:
    """调用 rtV3 接口，返回完整 JSON。失败抛异常。"""
    envelope = build_envelope(method, args)
    sign = compute_sign(envelope)
    rid = datetime.now().strftime("%Y%m%d%H%M%S") + "".join(
        random.choices(string.ascii_letters + string.digits, k=23)
    )
    headers = {
        "accept": "application/json, text/plain, */*",
        "requestid": rid,
        "sign": sign,
        "appversion": SPZH_APP_VERSION,
        "rnversion": SPZH_RN_VERSION,
        "content-type": "application/json",
        "accept-encoding": "gzip",
        "user-agent": "okhttp/3.12.13",
    }
    resp = requests.post(SPZH_API_URL, json=envelope, headers=headers, timeout=timeout)
    return resp.json()


def auth_args(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    args = {"ctToken": SPZH_CT_TOKEN, "utToken": SPZH_UT_TOKEN, "userId": SPZH_USER_ID}
    if extra:
        args.update(extra)
    return args


def _ok(data: Dict[str, Any]) -> bool:
    return data.get("code") == 0


# ── 数据抓取封装（返回 DB 可直接入库的字典） ─────────────────────

def fetch_player_detail(zh_id: Any) -> Optional[Dict[str, Any]]:
    """选手详情：CombinationInfoHandler + combination_yield_detail_handler + 持仓权限统计。"""
    try:
        info = call("CombinationInfoHandler", auth_args({"combinationId": zh_id}))
        if not _ok(info):
            logger.warning(f"详情接口失败 {zh_id}: {info.get('message')}")
            return None
        yd = call("combination_yield_detail_handler", auth_args({"combinationId": zh_id}))
        hold = call("CombinationHoldPositionPermitHandler", auth_args({"combinationId": zh_id}))
    except Exception as e:
        logger.warning(f"获取详情异常 {zh_id}: {e}")
        return None

    d = info.get("data") or {}
    y = yd.get("data") or {} if _ok(yd) else {}
    h = hold.get("data") or {} if _ok(hold) else {}
    if isinstance(h, list):  # 兜底：个别情况下返回持仓列表
        h = {}

    win_cnt = _to_int(d.get("dealWinCnt"))
    fail_cnt = _to_int(d.get("dealfailCnt"))
    win_rate = 0.0
    if win_cnt + fail_cnt > 0:
        win_rate = round(win_cnt * 100.0 / (win_cnt + fail_cnt), 2)
    # 持仓权限接口有更完整的统计（仅授权选手返回）
    if h.get("dayWinRate") is not None:
        win_rate = _to_float(h.get("dayWinRate"))

    return {
        "zh_id": str(zh_id),
        "name": d.get("zuheName") or d.get("uidNick") or "",
        "followers": _to_int(d.get("concernCnt")),
        "total_return": _to_float(y.get("totalYieldRateView")),
        "daily_return": _to_float(y.get("dayYieldRateView")),
        "net_value": _to_float(y.get("netWorth")),
        "max_drawdown": _to_float(h.get("maxDrawdown")) if h.get("maxDrawdown") is not None
        else _to_float(d.get("maxDrawDown")),
        "win_rate": win_rate,
        "days": _to_int(d.get("yxts")),
        "concept": "",
        "intro": d.get("summary") or d.get("comment") or "",
        "user_id": d.get("userId") or "",
        "labels": [],
        "ranks": [],
    }


def fetch_positions(zh_id: Any) -> List[Dict[str, Any]]:
    """持仓明细：CombinationHoldPositionPermitHandler（按板块分组，展平）。"""
    try:
        data = call("CombinationHoldPositionPermitHandler", auth_args({"combinationId": zh_id}))
    except Exception as e:
        logger.warning(f"获取持仓异常 {zh_id}: {e}")
        return []
    if not _ok(data):
        code = data.get("code")
        if code in (9035, 30001):
            logger.info(f"持仓不可见 {zh_id}: {data.get('message')}")
        else:
            logger.warning(f"持仓接口失败 {zh_id}: {data.get('message')}")
        return []

    positions: List[Dict[str, Any]] = []
    for block in data.get("data") or []:
        for item in block.get("data") or []:
            try:
                positions.append({
                    "zh_id": str(zh_id),
                    "stock_name": item.get("__name", ""),
                    "stock_code": str(item.get("__code", "")).zfill(6),
                    "cost_price": _to_float(item.get("cbj")),
                    "current_price": _to_float(item.get("__zxjg")),
                    "profit_ratio": _to_float(item.get("webYkRate")),
                    "position_ratio": _to_float(item.get("holdPos")),
                    "update_time": "",
                })
            except Exception as e:
                logger.warning(f"解析持仓项失败 {zh_id}: {e}")
    return positions


def fetch_trades(zh_id: Any, max_pages: int = 10) -> List[Dict[str, Any]]:
    """调仓记录：CombinationRelocatePositionHandler（分页拉取）。"""
    trades: List[Dict[str, Any]] = []
    page = 1
    page_size = 50
    try:
        while page <= max_pages:
            data = call("CombinationRelocatePositionHandler", auth_args({
                "combinationId": zh_id, "pageNum": page, "pageSize": page_size, "isLastDay": False,
            }))
            if not _ok(data):
                code = data.get("code")
                if code in (9035, 30001):
                    logger.info(f"调仓不可见 {zh_id}: {data.get('message')}")
                else:
                    logger.warning(f"调仓接口失败 {zh_id}: {data.get('message')}")
                break
            pages = (data.get("data") or {}).get("pages") or []
            for t in pages:
                try:
                    qty = _to_int(t.get("relocateQty"))
                    price = _to_float(t.get("relocatePrice"))
                    trades.append({
                        "zh_id": str(zh_id),
                        "stock_name": t.get("stkName", ""),
                        "stock_code": str(t.get("stkCode", "")).zfill(6),
                        # 历史调仓响应不含数量：有数量存数量，否则按 1 笔计
                        "trades": qty if qty else 1,
                        "position_ratio": t.get("positionRatio", ""),
                        "position_value": round(qty * price, 2) if qty else price,
                        "trade_date": t.get("relocateTime", ""),
                        "direction": "买入" if t.get("bsMark") == "B" else "卖出",
                        "position_change": 0,
                    })
                except Exception as e:
                    logger.warning(f"解析调仓项失败 {zh_id}: {e}")
            total_pages = _to_int((data.get("data") or {}).get("totalPages"))
            if page >= total_pages or total_pages == 0:
                break
            page += 1
    except Exception as e:
        logger.warning(f"获取调仓异常 {zh_id}: {e}")
    return trades


def follow_player(zh_id: Any) -> bool:
    """关注选手（持仓/调仓可见的前提之一）。"""
    try:
        url = "https://spzhapi.dfcfs.cn/srtV1"
        params = {
            "type": "rt_add_concern",
            "ctToken": SPZH_CT_TOKEN,
            "utToken": SPZH_UT_TOKEN,
            "appVer": "11002002",
            "zh": zh_id,
            "userId": SPZH_USER_ID,
        }
        r = requests.get(url, params=params, timeout=15)
        d = r.json()
        ok = str(d.get("result")) == "0"
        if not ok:
            logger.warning(f"关注失败 {zh_id}: {d.get('message')}")
        return ok
    except Exception as e:
        logger.warning(f"关注异常 {zh_id}: {e}")
        return False


def get_followed_ids() -> List[str]:
    """获取当前已关注的组合 ID 列表。"""
    try:
        data = call("FollowCombinationQueryHandler", auth_args())
        if not _ok(data):
            logger.warning(f"获取关注列表失败: {data.get('message')}")
            return []
        return (data.get("data") or {}).get("followCidList") or []
    except Exception as e:
        logger.warning(f"获取关注列表异常: {e}")
        return []


def unfollow_player(zh_id: Any) -> bool:
    """取消关注选手（释放自选组合名额）。"""
    try:
        url = "https://spzhapi.dfcfs.cn/srtV1"
        params = {
            "type": "rt_cancel_concern",
            "ctToken": SPZH_CT_TOKEN,
            "utToken": SPZH_UT_TOKEN,
            "appVer": "11002002",
            "zh": zh_id,
            "userId": SPZH_USER_ID,
        }
        r = requests.get(url, params=params, timeout=15)
        d = r.json()
        ok = str(d.get("result")) == "0"
        if not ok:
            logger.warning(f"取消关注失败 {zh_id}: {d.get('message')}")
        return ok
    except Exception as e:
        logger.warning(f"取消关注异常 {zh_id}: {e}")
        return False


def unfollow_all() -> int:
    """一键取消关注全部已关注的组合。返回成功取消的数量。"""
    ids = get_followed_ids()
    if not ids:
        logger.info("当前没有关注的组合")
        return 0
    logger.info(f"当前关注 {len(ids)} 个组合，开始取消...")
    ok = 0
    for zh in ids:
        if unfollow_player(zh):
            ok += 1
        time.sleep(0.1)
    logger.info(f"取消关注完成: {ok}/{len(ids)}")
    return ok


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default

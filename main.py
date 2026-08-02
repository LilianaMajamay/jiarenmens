"""
东方财富实盘选手爬虫（新接口版）

架构：
1. 获取选手列表（旧榜单 API rtV1/rt_get_rank，仍可用且字段更全）
2. 线程池并发爬取选手详情 + 持仓 + 调仓（新接口 spzhapi.dfcfs.cn/rtV3）
3. 批量原子写入 SQLite
4. 断点续传（检查点）

说明：持仓/调仓需要「关注选手」且选手授权公开；--follow 可自动关注。
"""
import json
import random
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any, Dict, List, Optional, Set, Tuple

from src.spiders.player_list import PlayerListSpider
from src.spiders.player_detail import crawl_player_detail
from src.spiders.position import crawl_positions
from src.spiders.trade import crawl_trades
from src.api import spzh_client
from src.storage.storage_factory import get_storage
from src.utils.logger import setup_logger
from src.config import DATA_DIR, BATCH_SIZE, CHECKPOINT_INTERVAL, DEFAULT_LIMIT, DEFAULT_WORKERS

logger = setup_logger()

CHECKPOINT_FILE = DATA_DIR / "checkpoint.json"

# 全局中断标志
INTERRUPTED = threading.Event()


def _signal_handler(signum, frame):
    logger.info("收到中断信号，正在保存数据...")
    INTERRUPTED.set()


# =============================================================================
# 检查点管理
# =============================================================================

def load_checkpoint() -> Dict[str, Any]:
    """加载检查点，不存在时返回初始状态。"""
    if not CHECKPOINT_FILE.exists():
        return {'last_index': 0, 'completed_ids': [], 'last_list_update': None, 'start_time': None}
    try:
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"加载检查点失败: {e}")
        return {'last_index': 0, 'completed_ids': [], 'last_list_update': None, 'start_time': None}


def save_checkpoint(state: Dict[str, Any]) -> None:
    """原子写入检查点。"""
    try:
        CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CHECKPOINT_FILE.with_suffix(".tmp")
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, separators=(',', ':'))
        tmp.replace(CHECKPOINT_FILE)
    except Exception as e:
        logger.warning(f"保存检查点失败: {e}")


# =============================================================================
# 批量刷盘
# =============================================================================

def flush_batch(storage, players: List, positions_data: List[tuple], trades_data: List[tuple], crawl_date: str) -> None:
    """将一批选手数据原子写入数据库。"""
    if not any([players, positions_data, trades_data]):
        return
    count_p = len(players)
    count_ps = sum(len(p[1]) for p in positions_data) if positions_data else 0
    count_tr = sum(len(t[1]) for t in trades_data) if trades_data else 0
    storage.flush_all(players, positions_data, trades_data, crawl_date)
    logger.debug(f"批量写入: {count_p}选手, {count_ps}持仓, {count_tr}调仓")


# =============================================================================
# 爬取单个选手
# =============================================================================

def crawl_player_data(
    player: Dict[str, Any],
    follow: bool = False,
) -> Tuple[str, str, Optional[Dict], List, List]:
    """爬取单个选手的详情、持仓、调仓数据（同步）。"""
    zh_id = player.get('zh_id', '')
    name = player.get('name', '')

    # 随机小延迟，降低触发 WAF 限流（9081）的概率
    time.sleep(random.uniform(0, 0.2))

    try:
        # 持仓/调仓需要关注；先关注，详情里的统计（胜率/回撤）才能拿到
        if follow:
            spzh_client.follow_player(zh_id)

        detail = crawl_player_detail(zh_id, player)
        if detail is None:
            return zh_id, name, None, [], []

        positions = crawl_positions(zh_id)
        trades = crawl_trades(zh_id)
        return zh_id, name, detail, positions, trades
    except Exception as e:
        logger.error(f"爬取选手 {name}({zh_id}) 失败: {e}")
        return zh_id, name, None, [], []


def crawl_all_data(
    players: List[Dict[str, Any]],
    storage,
    max_workers: int = 20,
    skip_existing: bool = True,
    checkpoint_interval: Optional[int] = None,
    follow: bool = False,
) -> Tuple[int, int, int]:
    """
    并发爬取所有选手数据。

    Returns:
        (success_count, skip_count, fail_count)
    """
    if checkpoint_interval is None:
        checkpoint_interval = CHECKPOINT_INTERVAL

    checkpoint = load_checkpoint()
    completed_ids: Set[str] = set(checkpoint.get('completed_ids', []))
    start_time = checkpoint.get('start_time') or time.time()
    crawl_date = date.today().isoformat()

    logger.info(f"检查点: 已完成 {len(completed_ids)} 个选手 | 本次爬取日期: {crawl_date}")

    # 缓冲区
    pending_players: List = []
    pending_positions: List[tuple] = []
    pending_trades: List[tuple] = []

    success = skip = failed = 0
    total = len(players)

    def run_one(p: Dict[str, Any]) -> Tuple:
        zh_id = p.get('zh_id', '')
        if INTERRUPTED.is_set() or (skip_existing and zh_id in completed_ids):
            return zh_id, p.get('name', ''), None, [], []
        return crawl_player_data(p, follow=follow)

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(run_one, p) for p in players]
            for i, future in enumerate(as_completed(futures), 1):
                try:
                    zh_id, name, detail, positions, trades = future.result()
                except Exception as e:
                    logger.error(f"任务异常: {e}")
                    continue

                if detail:
                    success += 1
                    completed_ids.add(zh_id)
                    pending_players.append(detail)
                    if positions:
                        pending_positions.append((zh_id, positions))
                    if trades:
                        pending_trades.append((zh_id, trades))
                    logger.info(f"  [+] [{i}/{total}] {name}({zh_id}): {len(positions)}持仓, {len(trades)}调仓")
                else:
                    if zh_id in completed_ids:
                        skip += 1
                    else:
                        failed += 1
                        logger.warning(f"  [x] [{i}/{total}] {name}({zh_id}): 获取失败")

                # 满批或到检查点 → 刷盘
                if len(pending_players) >= BATCH_SIZE or i % checkpoint_interval == 0:
                    flush_batch(storage, pending_players, pending_positions, pending_trades, crawl_date)
                    pending_players.clear()
                    pending_positions.clear()
                    pending_trades.clear()

                if i % checkpoint_interval == 0:
                    checkpoint['completed_ids'] = list(completed_ids)
                    checkpoint['start_time'] = start_time
                    save_checkpoint(checkpoint)
                    logger.info(f"  [检查点] 进度 {i}/{total}")

                if INTERRUPTED.is_set():
                    logger.info("爬取中断")
                    break
    finally:
        # 最终刷盘
        flush_batch(storage, pending_players, pending_positions, pending_trades, crawl_date)
        checkpoint['completed_ids'] = list(completed_ids)
        checkpoint['start_time'] = start_time
        save_checkpoint(checkpoint)

    logger.info("\n" + "=" * 60)
    logger.info(f"完成! 成功: {success}, 跳过: {skip}, 失败: {failed}")
    logger.info("=" * 60)
    return success, skip, failed


# =============================================================================
# 命令行入口
# =============================================================================

def check_env() -> int:
    """运行环境自检：依赖 / .env 令牌 / 接口连通性。返回 0 全部就绪。"""
    print("=" * 50)
    print("运行环境自检")
    print("=" * 50)
    ok = True

    # 1) 依赖
    deps = {"requests": "HTTP", "gmssl": "SM4签名", "dotenv": ".env加载"}
    for mod, desc in deps.items():
        try:
            __import__(mod)
            print(f"  [✓] 依赖 {mod} ({desc})")
        except ImportError:
            print(f"  [✗] 缺少依赖 {mod} ({desc})，请先: pip install -r requirements.txt")
            ok = False

    # 2) .env / 令牌
    from src.config import SPZH_CT_TOKEN, SPZH_UT_TOKEN, SPZH_USER_ID, SPZH_DEVICE_ID
    env_file = DATA_DIR.parent / ".env"
    if not env_file.exists():
        print(f"  [✗] 未找到 .env（请先: cp .env.example .env 并填入令牌）")
        ok = False
    for name, val in [("SPZH_CT_TOKEN", SPZH_CT_TOKEN), ("SPZH_UT_TOKEN", SPZH_UT_TOKEN),
                      ("SPZH_USER_ID", SPZH_USER_ID), ("SPZH_DEVICE_ID", SPZH_DEVICE_ID)]:
        if val:
            print(f"  [✓] {name} 已配置")
        else:
            print(f"  [✗] {name} 为空，请填入 .env")
            ok = False

    # 3) 接口连通性
    from src.api import spzh_client
    try:
        d = spzh_client.call("QualifyingConfigHandler", {"ctToken": "", "utToken": "", "userId": ""})
        if d.get("code") == 0:
            print("  [✓] 接口连通（QualifyingConfigHandler 正常）")
        else:
            print(f"  [✗] 接口异常: {d.get('message')} (code={d.get('code')})")
            ok = False
    except Exception as e:
        print(f"  [✗] 网络/接口异常: {e}")
        ok = False

    # 4) 令牌有效性（带登录态的接口）
    try:
        d = spzh_client.call("FollowCombinationQueryHandler", spzh_client.auth_args())
        if d.get("code") == 0:
            print("  [✓] 会话令牌有效（可正常调用登录接口）")
        else:
            print(f"  [✗] 会话令牌无效: {d.get('message')} (code={d.get('code')})")
            print("      令牌可能已过期，需要重新抓包，见 docs/抓包环境搭建.md")
            ok = False
    except Exception as e:
        print(f"  [✗] 令牌校验异常: {e}")
        ok = False

    print("=" * 50)
    print("结论:", "全部就绪，可以开始爬取 ✓" if ok else "存在未就绪项，请按提示处理 ✗")
    return 0 if ok else 1


def main():
    import argparse

    parser = argparse.ArgumentParser(description='东方财富实盘选手爬虫')
    parser.add_argument('--test', action='store_true', help='测试模式(只处理10个选手)')
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT, help=f'每榜单爬取数量 (default: {DEFAULT_LIMIT})')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS, help=f'并发数 (default: {DEFAULT_WORKERS})')
    parser.add_argument('--no-skip', action='store_true', help='不跳过已存在的选手数据')
    parser.add_argument('--checkpoint-reset', action='store_true', help='重置检查点')
    parser.add_argument('--follow', action='store_true',
                        help='自动关注选手（持仓/调仓可见的前提；注意自选组合有上限，建议分批）')
    parser.add_argument('--analyze', action='store_true', help='运行持仓分析')
    parser.add_argument('--board', type=str, default=None,
                        help='分析指定榜单: 总榜/年榜/月榜/周榜/日榜 (配合 --analyze)')
    parser.add_argument('--unfollow', action='store_true',
                        help='一键取消关注全部已关注的组合（释放自选组合名额）')
    parser.add_argument('--check', action='store_true', help='检查运行环境与令牌是否就绪（爬取前自检）')
    args = parser.parse_args()

    if args.check:
        sys.exit(check_env())

    if args.analyze:
        from src.analysis.position_analyzer import analyze_positions
        analyze_positions(board=args.board)
        return

    if args.unfollow:
        from src.api import spzh_client
        count = spzh_client.unfollow_all()
        logger.info(f"一键取消关注完成，共取消 {count} 个组合")
        return

    if args.checkpoint_reset and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        logger.info("检查点已重置")

    storage = get_storage()

    logger.info("=" * 60)
    logger.info(f"东方财富实盘选手爬虫 | 每榜单: {args.limit}名 | 并发: {args.workers}")
    logger.info("=" * 60)

    # Step 1: 获取选手列表
    logger.info("\n[Step 1] 获取选手列表...")
    players = PlayerListSpider().fetch_player_list(args.limit)
    if not players:
        logger.warning("未获取到选手列表")
        return
    logger.info(f"共 {len(players)} 个选手 (去重后)")

    if args.test:
        players = players[:10]
        logger.info(f"测试模式: 只处理前 10 个")

    # Step 2: 并发爬取
    logger.info(f"\n[Step 2] 并发爬取 (并发={args.workers}, 跳过已存在={not args.no_skip}, 自动关注={args.follow})...")
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    try:
        crawl_all_data(
            players, storage,
            max_workers=args.workers,
            skip_existing=not args.no_skip,
            follow=args.follow,
        )
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.exception(f"未处理异常: {e}")


if __name__ == "__main__":
    main()

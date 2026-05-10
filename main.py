"""
东方财富实盘选手爬虫

功能：
- 异步 Playwright 并发爬取
- SQLite 高效存储
- 增量更新 + 断点续传
- 批量写入优化
"""
import asyncio
import json
import signal
import sys
import time
from pathlib import Path
from datetime import date
from typing import List, Dict, Any, Tuple, Optional

from src.spiders.player_list import PlayerListSpider
from src.spiders.player_detail import crawl_player_detail_async
from src.spiders.position import crawl_positions_async
from src.spiders.trade import crawl_trades_async
from src.storage.storage_factory import get_storage
from src.utils.logger import setup_logger
from src.utils.async_playwright_pool import AsyncPlaywrightPool

logger = setup_logger()

# 检查点文件
CHECKPOINT_FILE = Path(__file__).parent / "data" / "checkpoint.json"

# 批量保存配置
BATCH_SIZE = 50


# =============================================================================
# 检查点管理
# =============================================================================

def load_checkpoint() -> Dict[str, Any]:
    """加载检查点"""
    if not CHECKPOINT_FILE.exists():
        return {
            'last_index': 0,
            'completed_ids': [],
            'last_list_update': None,
            'start_time': None
        }

    try:
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"加载检查点失败: {e}")
        return {
            'last_index': 0,
            'completed_ids': [],
            'last_list_update': None,
            'start_time': None
        }


def save_checkpoint(state: Dict[str, Any]):
    """保存检查点（原子写入，防止进程中断时文件损坏）"""
    try:
        CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = CHECKPOINT_FILE.with_suffix(".tmp")
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, separators=(',', ':'))
        tmp_file.replace(CHECKPOINT_FILE)
    except Exception as e:
        logger.warning(f"保存检查点失败: {e}")


# =============================================================================
# 异步爬取核心
# =============================================================================

async def crawl_player_data_async(
    zh_id: str,
    name: str,
    pool: AsyncPlaywrightPool,
    skip_existing: bool = True
) -> Tuple[str, str, Optional[Dict], List, List]:
    """
    异步爬取单个选手的所有数据（真正并行）

    Args:
        zh_id: 选手ID
        name: 选手名称
        pool: 异步 Playwright 连接池
        skip_existing: 是否跳过已存在的

    Returns:
        (zh_id, name, detail, positions, trades)
    """
    try:
        # 三个请求真正并行
        detail, positions, trades = await asyncio.gather(
            crawl_player_detail_async(zh_id, pool),
            crawl_positions_async(zh_id, "", pool),
            crawl_trades_async(zh_id, "", pool),
            return_exceptions=True
        )

        # 处理异常
        if isinstance(detail, Exception):
            logger.error(f"获取详情失败 {zh_id}: {detail}")
            detail = None
        if isinstance(positions, Exception):
            logger.error(f"获取持仓失败 {zh_id}: {positions}")
            positions = []
        if isinstance(trades, Exception):
            logger.error(f"获取调仓失败 {zh_id}: {trades}")
            trades = []

        return (zh_id, name, detail, positions or [], trades or [])

    except Exception as e:
        logger.error(f"爬取选手 {name}({zh_id}) 失败: {e}")
        return (zh_id, name, None, [], [])


async def crawl_all_data_async(
    players: List[Dict[str, Any]],
    storage,
    max_workers: int = 20,
    skip_existing: bool = True,
    checkpoint_interval: int = 50
):
    """
    异步爬取所有选手数据

    Args:
        players: 选手列表
        storage: 存储实例
        max_workers: 最大并发数
        skip_existing: 是否跳过已存在的
        checkpoint_interval: 检查点保存间隔
    """
    # 加载检查点
    checkpoint = load_checkpoint()
    completed_ids = set(checkpoint.get('completed_ids', []))
    start_time = checkpoint.get('start_time') or time.time()

    # 本次爬取日期
    crawl_date = date.today().isoformat()

    logger.info(f"检查点: 已完成 {len(completed_ids)} 个选手")
    logger.info(f"本次爬取日期: {crawl_date}")

    # 创建连接池
    pool = AsyncPlaywrightPool(pool_size=max_workers)
    await pool.initialize()

    # 批量数据缓冲区
    pending_players = []
    pending_positions = []
    pending_trades = []

    try:
        # 信号处理
        loop = asyncio.get_event_loop()
        interrupted = False

        def signal_handler():
            nonlocal interrupted
            logger.info("收到中断信号，正在保存检查点和数据...")
            interrupted = True
            # 保存剩余数据
            _flush_batch(storage, pending_players, pending_positions, pending_trades, crawl_date)
            checkpoint['completed_ids'] = list(completed_ids)
            checkpoint['start_time'] = start_time
            save_checkpoint(checkpoint)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                pass

        # 创建信号量控制并发
        semaphore = asyncio.Semaphore(max_workers)

        async def crawl_with_semaphore(player: Dict[str, Any]) -> Tuple[str, str, Any, List, List]:
            zh_id = player.get('zh_id')
            name = player.get('name', '')

            async with semaphore:
                if interrupted:
                    return (zh_id, name, None, [], [])

                # 跳过已完成的
                if zh_id in completed_ids:
                    player_data = storage.load_player(zh_id) if hasattr(storage, 'load_player') else None
                    positions = storage.load_positions(zh_id) if hasattr(storage, 'load_positions') else []
                    trades = storage.load_trades(zh_id) if hasattr(storage, 'load_trades') else []
                    return (zh_id, name, player_data, positions, trades)

                return await crawl_player_data_async(zh_id, name, pool, skip_existing)

        def _flush_batch(storage, players_buf, positions_buf, trades_buf, crawl_date):
            """批量保存数据"""
            if players_buf:
                storage.save_players_batch(players_buf)
                logger.debug(f"批量保存 {len(players_buf)} 个选手")
            if positions_buf:
                storage.save_positions_batch(positions_buf, crawl_date)
                logger.debug(f"批量保存 {len(positions_buf)} 条持仓记录")
            if trades_buf:
                storage.save_trades_batch(trades_buf, crawl_date)
                logger.debug(f"批量保存 {len(trades_buf)} 条调仓记录")

        # 创建所有任务
        tasks = [crawl_with_semaphore(p) for p in players]

        # 异步执行
        success_count = 0
        fail_count = 0
        skip_count = 0

        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            result = await coro
            zh_id, name, detail, positions, trades = result

            if detail:
                success_count += 1
                completed_ids.add(zh_id)
                pending_players.append(detail)
                if positions:
                    pending_positions.append((zh_id, positions))
                if trades:
                    pending_trades.append((zh_id, trades))
                logger.info(f"  ✓ [{i}/{len(players)}] {name}({zh_id}): {len(positions)}持仓, {len(trades)}调仓")

                # 批量保存
                if len(pending_players) >= BATCH_SIZE:
                    _flush_batch(storage, pending_players, pending_positions, pending_trades, crawl_date)
                    pending_players.clear()
                    pending_positions.clear()
                    pending_trades.clear()
            else:
                if zh_id in completed_ids:
                    skip_count += 1
                else:
                    fail_count += 1
                    logger.warning(f"  ✗ [{i}/{len(players)}] {name}({zh_id}): 获取失败")

            # 保存检查点
            if i % checkpoint_interval == 0:
                _flush_batch(storage, pending_players, pending_positions, pending_trades, crawl_date)
                pending_players.clear()
                pending_positions.clear()
                pending_trades.clear()
                checkpoint['completed_ids'] = list(completed_ids)
                checkpoint['start_time'] = start_time
                save_checkpoint(checkpoint)
                logger.info(f"  [检查点已保存] 进度: {i}/{len(players)}")

            if interrupted:
                logger.info("爬取被中断，已保存数据")
                break

        # 最终批量保存
        _flush_batch(storage, pending_players, pending_positions, pending_trades, crawl_date)

        # 最终检查点
        checkpoint['completed_ids'] = list(completed_ids)
        checkpoint['start_time'] = start_time
        save_checkpoint(checkpoint)

        logger.info("\n" + "=" * 60)
        logger.info(f"数据爬取完成! 成功: {success_count}, 跳过: {skip_count}, 失败: {fail_count}")
        logger.info("=" * 60)

        return success_count, skip_count, fail_count

    finally:
        await pool.close()


# =============================================================================
# 主入口
# =============================================================================

def main():
    """主函数"""
    import argparse

    # 先检查是否有--analyze
    if '--analyze' in sys.argv:
        from src.analysis.position_analyzer import analyze_positions
        sys.argv = [a for a in sys.argv if a != '--analyze']
        analyze_positions()
        return

    parser = argparse.ArgumentParser(description='东方财富实盘选手爬虫')
    parser.add_argument('--test', action='store_true', help='测试模式(只处理10个选手)')
    parser.add_argument('--limit', type=int, default=500, help='每榜单爬取数量(default: 500)')
    parser.add_argument('--workers', type=int, default=20, help='并发数(default: 20)')
    parser.add_argument('--no-skip', action='store_true', help='不跳过已存在的文件')
    parser.add_argument('--checkpoint-reset', action='store_true', help='重置检查点')
    args = parser.parse_args()

    skip_existing = not args.no_skip

    # 重置检查点
    if args.checkpoint_reset and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        logger.info("检查点已重置")

    # 确定存储
    storage = get_storage()

    logger.info("=" * 60)
    logger.info(f"东方财富实盘选手爬虫")
    logger.info(f"每榜单: {args.limit}名, 并发数: {args.workers}, 批量大小: {BATCH_SIZE}")
    logger.info(f"存储模式: SQLite")
    logger.info("=" * 60)

    # Step 1: 获取选手列表
    logger.info("\n[Step 1] 获取选手列表...")
    player_list_spider = PlayerListSpider()
    players = player_list_spider.fetch_player_list(args.limit)

    if not players:
        logger.warning("未获取到选手列表")
        return

    logger.info(f"共获取 {len(players)} 个选手 (去重后)")

    if args.test:
        players = players[:10]
        logger.info(f"测试模式: 只处理前 {len(players)} 个选手")

    # Step 2: 异步爬取
    logger.info(f"\n[Step 2] 异步获取选手数据 (并发数={args.workers}, 跳过已存在={skip_existing})...")

    try:
        asyncio.run(crawl_all_data_async(
            players,
            storage,
            max_workers=args.workers,
            skip_existing=skip_existing
        ))
    except KeyboardInterrupt:
        logger.info("爬取被用户中断")


if __name__ == "__main__":
    main()
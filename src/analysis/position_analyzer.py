"""
持仓分析器
- 统计持仓数量最多的股票
- 分析当日选手仓位分布
- 热门股票分析

使用 SQLite 存储
"""
import json
from pathlib import Path
from typing import List, Dict, Any

from src.storage.storage_factory import get_storage
from src.utils.logger import setup_logger

logger = setup_logger()


class PositionAnalyzer:
    """持仓分析器"""

    def __init__(self, storage=None):
        self.storage = storage or get_storage()

    def get_all_positions(self, crawl_date: str | None = None) -> List[Dict[str, Any]]:
        """获取所有选手的持仓数据"""
        return self.storage.get_all_positions(crawl_date)

    def get_top_holdings(self, top_n: int = 20, crawl_date: str | None = None) -> List[Dict[str, Any]]:
        """获取持仓数量最多的股票"""
        return self.storage.get_top_holdings(top_n, crawl_date)

    def get_position_distribution(self, crawl_date: str | None = None) -> Dict[str, int]:
        """获取选手仓位分布"""
        return self.storage.get_position_distribution(crawl_date)

    def get_sector_distribution(self, crawl_date: str | None = None) -> List[Dict[str, Any]]:
        """获取概念板块分布"""
        return self.storage.get_sector_distribution(crawl_date)

    def get_top_performers(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """获取当日盈利最高的选手"""
        return self.storage.get_top_performers(top_n)

    def generate_report(self, board: str | None = None) -> Dict[str, Any]:
        """生成完整分析报告（使用最新爬取日期，可选按榜单过滤）"""
        return self.storage.generate_report(board)

    def save_report(self, output_path: str | None = None, board: str | None = None) -> Dict[str, Any]:
        """保存分析报告"""
        report = self.generate_report(board)

        if output_path is None:
            from src.config import DATA_DIR
            output_path = DATA_DIR / "analysis_report.json"

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"分析报告已保存到 {output_path}")
        return report


def _normalize_board(board: str) -> str:
    """把 总/年/月/周/日 等简写归一为 总榜/年榜/月榜/周榜/日榜。"""
    if not board:
        return board
    board = board.strip()
    if board.endswith("榜"):
        return board
    if board in ("总", "年", "月", "周", "日"):
        return board + "榜"
    return board


def analyze_positions(board: str | None = None):
    """命令行分析入口"""
    analyzer = PositionAnalyzer()
    report = analyzer.generate_report(_normalize_board(board))

    crawl_date = report.get('crawl_date', '未知')
    board_text = report.get('board') or '全部'
    print("\n" + "=" * 50)
    print(f"持仓分析报告 ({crawl_date}) [{board_text}]")
    print("=" * 50)
    print(f"\n【概览】")
    print(f"  选手总数: {report['summary']['total_players']}")
    print(f"  持仓记录: {report['summary']['total_positions']}")
    print(f"  涉及股票: {report['summary']['unique_stocks']}只")

    print(f"\n【持仓最多的股票 Top 10】")
    for i, h in enumerate(report['top_holdings'][:10], 1):
        print(f"  {i}. {h['stock_name']}({h['stock_code']}): "
              f"{h['holder_count']}人持有, 平均仓位{h['avg_position_ratio']:.1f}%, 平均盈利{h['avg_profit_ratio']:.2f}%")

    print(f"\n【仓位分布】")
    for k, v in sorted(report['position_distribution'].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}人")

    print(f"\n【当日盈利Top 10】")
    for i, p in enumerate(report['top_performers'][:10], 1):
        print(f"  {i}. {p['name']}: 日{p['daily_return']:.2f}%, 总{p['total_return']:.2f}%")

    print()


if __name__ == "__main__":
    analyze_positions()

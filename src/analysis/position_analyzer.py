"""
持仓分析器
- 统计持仓数量最多的股票
- 分析当日选手仓位分布
- 热门股票分析

使用 SQLite 存储
"""
import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Any

from src.storage.sqlite_storage import SQLiteStorage
from src.storage.storage_factory import get_storage
from src.utils.logger import setup_logger

logger = setup_logger()

# 默认存储
_default_storage = None


def _get_default_storage():
    """获取默认存储"""
    global _default_storage
    if _default_storage is None:
        _default_storage = get_storage()
    return _default_storage


class PositionAnalyzer:
    """持仓分析器"""

    def __init__(self, storage=None):
        self.storage = storage or _get_default_storage()

    def get_all_positions(self) -> List[Dict[str, Any]]:
        """获取所有选手的持仓数据"""
        return self.storage.get_all_positions()

    def get_top_holdings(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """获取持仓数量最多的股票"""
        return self.storage.get_top_holdings(top_n)

    def get_position_distribution(self) -> Dict[str, Any]:
        """获取选手仓位分布"""
        return self.storage.get_position_distribution()

    def get_sector_distribution(self) -> List[Dict[str, Any]]:
        """获取概念板块分布"""
        return self.storage.get_sector_distribution()

    def get_top_performers(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """获取当日盈利最高的选手"""
        return self.storage.get_top_performers(top_n)

    def generate_report(self) -> Dict[str, Any]:
        """生成完整分析报告"""
        logger.info("开始生成持仓分析报告...")

        player_ids = self.storage.get_all_player_ids()
        positions = self.storage.get_all_positions()
        unique_stocks = len(set(p.get('stock_code', '') for p in positions if p.get('stock_code')))

        report = {
            'summary': {
                'total_players': len(player_ids),
                'total_positions': len(positions),
                'unique_stocks': unique_stocks,
            },
            'top_holdings': self.get_top_holdings(20),
            'position_distribution': self.get_position_distribution(),
            'profit_distribution': self.get_sector_distribution(),
            'top_performers': self.get_top_performers(10),
        }

        logger.info(f"分析完成: {report['summary']['total_players']}选手, "
                    f"{report['summary']['total_positions']}持仓, "
                    f"{report['summary']['unique_stocks']}只股票")
        return report

    def save_report(self, output_path: str = None):
        """保存分析报告"""
        report = self.generate_report()

        if output_path is None:
            from src.config import DATA_DIR
            output_path = DATA_DIR / "analysis_report.json"

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"分析报告已保存到 {output_path}")
        return report


def analyze_positions():
    """命令行分析入口"""
    analyzer = PositionAnalyzer()
    report = analyzer.generate_report()

    print("\n" + "=" * 50)
    print("持仓分析报告")
    print("=" * 50)
    print(f"\n【概览】")
    print(f"  选手总数: {report['summary']['total_players']}")
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
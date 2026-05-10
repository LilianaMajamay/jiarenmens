"""
SQLite 数据仓库

高性能存储实现，支持：
- WAL 模式并发读写
- 批量插入
- 索引优化
- SQL 分析查询
"""
import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from contextlib import contextmanager
from datetime import datetime

from src.storage.interface import StorageInterface
from src.utils.logger import setup_logger

logger = setup_logger()


class SQLiteStorage(StorageInterface):
    """
    SQLite 数据仓库

    表结构：
    - players: 选手详情
    - positions: 持仓数据
    - trades: 调仓记录
    """

    def __init__(self, db_path: Path = None):
        if db_path is None:
            from src.config import DATA_DIR
            db_path = DATA_DIR / "crawl_data.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _init_db(self):
        """初始化数据库表结构"""
        with self.get_connection() as conn:
            # WAL 模式 - 支持并发读写
            conn.execute("PRAGMA journal_mode=WAL")
            # 同步级别 - 平衡性能和安全
            conn.execute("PRAGMA synchronous=NORMAL")
            # 外键约束
            conn.execute("PRAGMA foreign_keys=ON")

            # Players 表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    zh_id TEXT PRIMARY KEY,
                    name TEXT DEFAULT '',
                    followers INTEGER DEFAULT 0,
                    total_return REAL DEFAULT 0.0,
                    daily_return REAL DEFAULT 0.0,
                    net_value REAL DEFAULT 0.0,
                    max_drawdown REAL DEFAULT 0.0,
                    win_rate REAL DEFAULT 0.0,
                    days INTEGER DEFAULT 0,
                    concept TEXT DEFAULT '',
                    intro TEXT DEFAULT '',
                    user_id TEXT DEFAULT '',
                    labels TEXT DEFAULT '[]',
                    ranks TEXT DEFAULT '[]',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Positions 表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zh_id TEXT NOT NULL,
                    stock_name TEXT DEFAULT '',
                    stock_code TEXT DEFAULT '',
                    cost_price REAL DEFAULT 0.0,
                    current_price REAL DEFAULT 0.0,
                    profit_ratio REAL DEFAULT 0.0,
                    position_ratio REAL DEFAULT 0.0,
                    update_time TEXT DEFAULT '',
                    crawl_date TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (zh_id) REFERENCES players(zh_id) ON DELETE CASCADE
                )
            """)

            # Trades 表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zh_id TEXT NOT NULL,
                    stock_name TEXT DEFAULT '',
                    stock_code TEXT DEFAULT '',
                    trades_count INTEGER DEFAULT 1,
                    position_ratio TEXT DEFAULT '',
                    position_value REAL DEFAULT 0.0,
                    trade_date TEXT DEFAULT '',
                    direction TEXT DEFAULT '',
                    position_change REAL DEFAULT 0.0,
                    crawl_date TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (zh_id) REFERENCES players(zh_id) ON DELETE CASCADE
                )
            """)

            # 索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_zh_id ON positions(zh_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_stock ON positions(stock_code)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_crawl_date ON positions(crawl_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_zh_id ON trades(zh_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_stock ON trades(stock_code)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(trade_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_crawl_date ON trades(crawl_date)")

            conn.commit()

        logger.info(f"SQLite 数据库初始化完成: {self.db_path}")

    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ---- 选手数据操作 ----

    def save_player(self, player: Dict[str, Any]) -> None:
        """保存单个选手"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO players (
                    zh_id, name, followers, total_return, daily_return,
                    net_value, max_drawdown, win_rate, days, concept, intro,
                    user_id, labels, ranks, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(zh_id) DO UPDATE SET
                    name=excluded.name,
                    followers=excluded.followers,
                    total_return=excluded.total_return,
                    daily_return=excluded.daily_return,
                    net_value=excluded.net_value,
                    max_drawdown=excluded.max_drawdown,
                    win_rate=excluded.win_rate,
                    days=excluded.days,
                    concept=excluded.concept,
                    intro=excluded.intro,
                    user_id=excluded.user_id,
                    labels=excluded.labels,
                    ranks=excluded.ranks,
                    updated_at=CURRENT_TIMESTAMP
            """, (
                player.get('zh_id'),
                player.get('name', ''),
                player.get('followers', 0),
                player.get('total_return', 0.0),
                player.get('daily_return', 0.0),
                player.get('net_value', 0.0),
                player.get('max_drawdown', 0.0),
                player.get('win_rate', 0.0),
                player.get('days', 0),
                player.get('concept', ''),
                player.get('intro', ''),
                player.get('user_id', ''),
                json.dumps(player.get('labels', [])),
                json.dumps(player.get('ranks', [])),
            ))

    def save_players(self, players: List[Dict[str, Any]], filename: str = "players.json") -> None:
        """批量保存选手列表（兼容 JSON 接口）"""
        for player in players:
            self.save_player(player)

    def save_players_batch(self, players: List[Dict[str, Any]]) -> None:
        """批量保存选手（高性能）"""
        if not players:
            return
        with self.get_connection() as conn:
            conn.executemany("""
                INSERT INTO players (
                    zh_id, name, followers, total_return, daily_return,
                    net_value, max_drawdown, win_rate, days, concept, intro,
                    user_id, labels, ranks, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(zh_id) DO UPDATE SET
                    name=excluded.name,
                    followers=excluded.followers,
                    total_return=excluded.total_return,
                    daily_return=excluded.daily_return,
                    net_value=excluded.net_value,
                    max_drawdown=excluded.max_drawdown,
                    win_rate=excluded.win_rate,
                    days=excluded.days,
                    concept=excluded.concept,
                    intro=excluded.intro,
                    user_id=excluded.user_id,
                    labels=excluded.labels,
                    ranks=excluded.ranks,
                    updated_at=CURRENT_TIMESTAMP
            """, [
                (
                    p.get('zh_id'),
                    p.get('name', ''),
                    p.get('followers', 0),
                    p.get('total_return', 0.0),
                    p.get('daily_return', 0.0),
                    p.get('net_value', 0.0),
                    p.get('max_drawdown', 0.0),
                    p.get('win_rate', 0.0),
                    p.get('days', 0),
                    p.get('concept', ''),
                    p.get('intro', ''),
                    p.get('user_id', ''),
                    json.dumps(p.get('labels', [])),
                    json.dumps(p.get('ranks', [])),
                )
                for p in players
            ])

    def save_positions_batch(self, data: List[tuple], crawl_date: str = None) -> None:
        """
        批量保存持仓（按日期去重，同一天只保留最新一次）

        Args:
            data: List of (zh_id, positions_list) tuples
            crawl_date: 爬取日期，格式如 '2026-03-24'
        """
        if not data:
            return
        if crawl_date is None:
            from datetime import date
            crawl_date = date.today().isoformat()
        with self.get_connection() as conn:
            for zh_id, positions in data:
                # 删除该选手该日期的旧数据
                conn.execute("DELETE FROM positions WHERE zh_id=? AND crawl_date=?", (zh_id, crawl_date))
                # 批量插入新数据
                if positions:
                    conn.executemany("""
                        INSERT INTO positions (
                            zh_id, stock_name, stock_code, cost_price, current_price,
                            profit_ratio, position_ratio, update_time, crawl_date, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, [
                        (
                            zh_id,
                            pos.get('stock_name', ''),
                            pos.get('stock_code', ''),
                            pos.get('cost_price', 0.0),
                            pos.get('current_price', 0.0),
                            pos.get('profit_ratio', 0.0),
                            pos.get('position_ratio', 0.0),
                            pos.get('update_time', ''),
                            crawl_date,
                        )
                        for pos in positions
                    ])

    def save_trades_batch(self, data: List[tuple], crawl_date: str = None) -> None:
        """
        批量保存调仓记录（按日期去重，同一天只保留最新一次）

        Args:
            data: List of (zh_id, trades_list) tuples
            crawl_date: 爬取日期，格式如 '2026-03-24'
        """
        if not data:
            return
        if crawl_date is None:
            from datetime import date
            crawl_date = date.today().isoformat()
        with self.get_connection() as conn:
            for zh_id, trades in data:
                # 删除该选手该日期的旧数据
                conn.execute("DELETE FROM trades WHERE zh_id=? AND crawl_date=?", (zh_id, crawl_date))
                # 批量插入新数据
                if trades:
                    conn.executemany("""
                        INSERT INTO trades (
                            zh_id, stock_name, stock_code, trades_count, position_ratio,
                            position_value, trade_date, direction, position_change, crawl_date, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, [
                        (
                            zh_id,
                            trade.get('stock_name', ''),
                            trade.get('stock_code', ''),
                            trade.get('trades', trade.get('trades_count', 1)),
                            trade.get('position_ratio', ''),
                            trade.get('position_value', 0.0),
                            trade.get('trade_date', ''),
                            trade.get('direction', ''),
                            trade.get('position_change', 0.0),
                            crawl_date,
                        )
                        for trade in trades
                    ])

    def load_player(self, zh_id: str) -> Optional[Dict[str, Any]]:
        """加载单个选手"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM players WHERE zh_id=?", (zh_id,)
            ).fetchone()

            if not row:
                return None

            return self._row_to_dict(row)

    def load_players(self, filename: str = "players.json") -> List[Dict[str, Any]]:
        """加载所有选手"""
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM players").fetchall()
            return [self._row_to_dict(row) for row in rows]

    def get_all_player_ids(self) -> Set[str]:
        """获取所有选手 ID"""
        with self.get_connection() as conn:
            rows = conn.execute("SELECT zh_id FROM players").fetchall()
            return {row['zh_id'] for row in rows}

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """将 Row 转换为字典"""
        d = dict(row)
        # 解析 JSON 字段
        for key in ['labels', 'ranks']:
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except json.JSONDecodeError:
                    d[key] = []
        return d

    # ---- 持仓数据操作 ----

    def save_positions(self, zh_id: str, positions: List[Dict[str, Any]]) -> None:
        """保存持仓数据（先删后插）"""
        with self.get_connection() as conn:
            # 删除旧数据
            conn.execute("DELETE FROM positions WHERE zh_id=?", (zh_id,))

            # 插入新数据
            for pos in positions:
                conn.execute("""
                    INSERT INTO positions (
                        zh_id, stock_name, stock_code, cost_price, current_price,
                        profit_ratio, position_ratio, update_time, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    zh_id,
                    pos.get('stock_name', ''),
                    pos.get('stock_code', ''),
                    pos.get('cost_price', 0.0),
                    pos.get('current_price', 0.0),
                    pos.get('profit_ratio', 0.0),
                    pos.get('position_ratio', 0.0),
                    pos.get('update_time', ''),
                ))

    def load_positions(self, zh_id: str) -> List[Dict[str, Any]]:
        """加载持仓数据"""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM positions WHERE zh_id=?", (zh_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    # ---- 调仓数据操作 ----

    def save_trades(self, zh_id: str, trades: List[Dict[str, Any]]) -> None:
        """保存调仓记录（先删后插）"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM trades WHERE zh_id=?", (zh_id,))

            for trade in trades:
                conn.execute("""
                    INSERT INTO trades (
                        zh_id, stock_name, stock_code, trades_count, position_ratio,
                        position_value, trade_date, direction, position_change, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    zh_id,
                    trade.get('stock_name', ''),
                    trade.get('stock_code', ''),
                    trade.get('trades', trade.get('trades_count', 1)),
                    trade.get('position_ratio', ''),
                    trade.get('position_value', 0.0),
                    trade.get('trade_date', ''),
                    trade.get('direction', ''),
                    trade.get('position_change', 0.0),
                ))

    def load_trades(self, zh_id: str) -> List[Dict[str, Any]]:
        """加载调仓记录"""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE zh_id=? ORDER BY trade_date DESC",
                (zh_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    # ---- 分析查询 ----

    def get_positions_by_date(self, crawl_date: str = None) -> List[Dict[str, Any]]:
        """获取指定日期的持仓数据"""
        if crawl_date is None:
            from datetime import date
            crawl_date = date.today().isoformat()
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT p.*, pl.name as player_name
                FROM positions p
                LEFT JOIN players pl ON p.zh_id = pl.zh_id
                WHERE p.crawl_date = ?
                ORDER BY p.position_ratio DESC
            """, (crawl_date,)).fetchall()
            return [dict(row) for row in rows]

    def get_trades_by_date(self, crawl_date: str = None) -> List[Dict[str, Any]]:
        """获取指定日期的调仓数据"""
        if crawl_date is None:
            from datetime import date
            crawl_date = date.today().isoformat()
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT t.*, pl.name as player_name
                FROM trades t
                LEFT JOIN players pl ON t.zh_id = pl.zh_id
                WHERE t.crawl_date = ?
                ORDER BY t.trade_date DESC
            """, (crawl_date,)).fetchall()
            return [dict(row) for row in rows]

    def get_top_holdings(self, top_n: int = 20, crawl_date: str = None) -> List[Dict[str, Any]]:
        """获取持仓最多的股票"""
        if crawl_date is None:
            from datetime import date
            crawl_date = date.today().isoformat()
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    stock_code,
                    stock_name,
                    COUNT(*) as holder_count,
                    AVG(position_ratio) as avg_position_ratio,
                    AVG(profit_ratio) as avg_profit_ratio
                FROM positions
                WHERE stock_code IS NOT NULL AND stock_code != '' AND crawl_date = ?
                GROUP BY stock_code
                ORDER BY holder_count DESC
                LIMIT ?
            """, (crawl_date, top_n)).fetchall()

            return [dict(row) for row in rows]

    def get_position_distribution(self) -> Dict[str, int]:
        """获取选手仓位分布"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    CASE
                        WHEN total_pos = 0 THEN '空仓'
                        WHEN total_pos < 10 THEN '1成以下'
                        WHEN total_pos < 30 THEN '3成以下'
                        WHEN total_pos < 50 THEN '3-5成'
                        WHEN total_pos < 70 THEN '5-7成'
                        WHEN total_pos < 90 THEN '7-9成'
                        ELSE '9成以上'
                    END as position_level,
                    COUNT(*) as player_count
                FROM (
                    SELECT zh_id, SUM(position_ratio) as total_pos
                    FROM positions
                    GROUP BY zh_id
                )
                GROUP BY position_level
                ORDER BY player_count DESC
            """).fetchall()

            return {row['position_level']: row['player_count'] for row in rows}

    def get_top_performers(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """获取当日盈利最高的选手"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT zh_id, name, daily_return, total_return
                FROM players
                ORDER BY daily_return DESC
                LIMIT ?
            """, (top_n,)).fetchall()

            return [dict(row) for row in rows]

    def get_all_positions(self) -> List[Dict[str, Any]]:
        """获取所有持仓数据"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT p.*, pl.name as player_name
                FROM positions p
                LEFT JOIN players pl ON p.zh_id = pl.zh_id
            """).fetchall()

            return [dict(row) for row in rows]

    def get_stock_followers(self, stock_code: str) -> List[Dict[str, Any]]:
        """获取持有某股票的所有选手"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    pl.zh_id,
                    pl.name,
                    pl.daily_return,
                    p.position_ratio,
                    p.profit_ratio
                FROM positions p
                JOIN players pl ON p.zh_id = pl.zh_id
                WHERE p.stock_code = ?
                ORDER BY p.position_ratio DESC
            """, (stock_code,)).fetchall()

            return [dict(row) for row in rows]

    def get_sector_distribution(self) -> List[Dict[str, Any]]:
        """获取概念板块分布"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    CASE
                        WHEN avg_profit < -10 THEN '<-10%'
                        WHEN avg_profit < -5 THEN '-10%~-5%'
                        WHEN avg_profit < 0 THEN '-5%~0%'
                        WHEN avg_profit < 5 THEN '0%~5%'
                        WHEN avg_profit < 10 THEN '5%~10%'
                        WHEN avg_profit < 20 THEN '10%~20%'
                        ELSE '>20%'
                    END as profit_range,
                    COUNT(*) as stock_count
                FROM (
                    SELECT
                        stock_code,
                        AVG(profit_ratio) as avg_profit
                    FROM positions
                    WHERE stock_code IS NOT NULL AND stock_code != ''
                    GROUP BY stock_code
                )
                GROUP BY profit_range
                ORDER BY profit_range
            """).fetchall()

            return [{'range': row['profit_range'], 'count': row['stock_count']} for row in rows]

    def get_player_trade_history(self, zh_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取选手调仓历史"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM trades
                WHERE zh_id = ?
                ORDER BY trade_date DESC
                LIMIT ?
            """, (zh_id, limit)).fetchall()

            return [dict(row) for row in rows]

    # ---- 工具方法 ----

    def exists(self, zh_id: str) -> bool:
        """检查选手数据是否存在"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM players WHERE zh_id=? LIMIT 1", (zh_id,)
            ).fetchone()
            return row is not None

    def get_player_count(self) -> int:
        """获取选手总数"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM players").fetchone()
            return row['cnt']

    def get_position_count(self) -> int:
        """获取持仓记录总数"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM positions").fetchone()
            return row['cnt']

    def get_trade_count(self) -> int:
        """获取调仓记录总数"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM trades").fetchone()
            return row['cnt']

    def get_last_update_time(self, zh_id: str) -> Optional[datetime]:
        """获取选手最后更新时间"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT updated_at FROM players WHERE zh_id=?", (zh_id,)
            ).fetchone()
            return datetime.fromisoformat(row['updated_at']) if row else None

    def is_stale(self, zh_id: str, max_age_hours: int = 1) -> bool:
        """检查数据是否过期"""
        last_update = self.get_last_update_time(zh_id)
        if not last_update:
            return True

        age = datetime.now() - last_update
        return age.total_seconds() > max_age_hours * 3600

    def close(self) -> None:
        """关闭连接（SQLite 不需要显式关闭）"""
        pass

    def generate_report(self) -> Dict[str, Any]:
        """生成完整分析报告"""
        player_ids = self.get_all_player_ids()
        positions = self.get_all_positions()
        unique_stocks = len(set(p.get('stock_code', '') for p in positions if p.get('stock_code')))

        return {
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

    def __repr__(self):
        return f"SQLiteStorage(db_path={self.db_path})"


if __name__ == "__main__":
    # 测试
    from pathlib import Path

    db_path = Path("/tmp/test_crawl.db")
    if db_path.exists():
        db_path.unlink()

    storage = SQLiteStorage(db_path)

    # 测试插入
    storage.save_player({
        'zh_id': 'test123',
        'name': '测试选手',
        'followers': 100,
        'daily_return': 2.5,
        'total_return': 15.3,
    })

    storage.save_positions('test123', [
        {'stock_code': '000001', 'stock_name': '平安银行', 'position_ratio': 30.0, 'profit_ratio': 5.2},
        {'stock_code': '000002', 'stock_name': '万科A', 'position_ratio': 20.0, 'profit_ratio': -1.3},
    ])

    # 测试查询
    print(f"Player: {storage.load_player('test123')}")
    print(f"Positions: {storage.load_positions('test123')}")
    print(f"Top holdings: {storage.get_top_holdings()}")
    print(f"Position dist: {storage.get_position_distribution()}")

    print("\nSQLiteStorage test passed!")

"""
存储接口抽象

定义统一的存储接口
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Set


class StorageInterface(ABC):
    """存储接口抽象类"""

    # ---- 选手数据 ----

    @abstractmethod
    def save_player(self, player: Dict[str, Any]) -> None:
        """保存单个选手详情"""
        pass

    @abstractmethod
    def save_players(self, players: List[Dict[str, Any]], filename: str = "players.json") -> None:
        """保存选手列表"""
        pass

    @abstractmethod
    def load_player(self, zh_id: str) -> Optional[Dict[str, Any]]:
        """加载单个选手详情"""
        pass

    @abstractmethod
    def load_players(self, filename: str = "players.json") -> List[Dict[str, Any]]:
        """加载选手列表"""
        pass

    @abstractmethod
    def get_all_player_ids(self) -> Set[str]:
        """获取所有选手 ID"""
        pass

    # ---- 持仓数据 ----

    @abstractmethod
    def save_positions(self, zh_id: str, positions: List[Dict[str, Any]]) -> None:
        """保存持仓数据"""
        pass

    @abstractmethod
    def load_positions(self, zh_id: str) -> List[Dict[str, Any]]:
        """加载持仓数据"""
        pass

    # ---- 调仓数据 ----

    @abstractmethod
    def save_trades(self, zh_id: str, trades: List[Dict[str, Any]]) -> None:
        """保存调仓记录"""
        pass

    @abstractmethod
    def load_trades(self, zh_id: str) -> List[Dict[str, Any]]:
        """加载调仓记录"""
        pass

    # ---- 分析查询 ----

    @abstractmethod
    def get_top_holdings(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """获取持仓最多的股票"""
        pass

    @abstractmethod
    def get_position_distribution(self) -> Dict[str, int]:
        """获取选手仓位分布"""
        pass

    @abstractmethod
    def get_top_performers(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """获取当日盈利最高的选手"""
        pass

    @abstractmethod
    def get_all_positions(self) -> List[Dict[str, Any]]:
        """获取所有选手的持仓数据"""
        pass

    # ---- 工具方法 ----

    @abstractmethod
    def exists(self, zh_id: str) -> bool:
        """检查选手数据是否存在"""
        pass

    @abstractmethod
    def close(self) -> None:
        """关闭连接"""
        pass
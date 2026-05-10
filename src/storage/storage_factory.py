"""
存储工厂

统一使用 SQLite 存储
"""
from pathlib import Path
from typing import Optional

from src.storage.interface import StorageInterface
from src.storage.sqlite_storage import SQLiteStorage
from src.utils.logger import setup_logger

logger = setup_logger()


def create_storage(db_path: Path = None) -> StorageInterface:
    """创建 SQLite 存储实例"""
    return SQLiteStorage(db_path=db_path)


def get_default_storage() -> StorageInterface:
    """获取默认存储实例"""
    return create_storage()


# 全局存储实例
_storage: Optional[StorageInterface] = None


def get_storage() -> StorageInterface:
    """获取全局存储实例（单例）"""
    global _storage
    if _storage is None:
        _storage = create_storage()
        logger.info(f"存储初始化完成: {type(_storage).__name__}")
    return _storage


def reset_storage():
    """重置全局存储实例（用于测试或切换存储类型）"""
    global _storage
    if _storage is not None:
        _storage.close()
        _storage = None


# 保持向后兼容
SQLITE_ENABLED = True
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(name: str = "dfcfshipan", level: int = logging.INFO) -> logging.Logger:
    """设置日志（支持自动轮转）"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台输出（Windows GBK 终端友好）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    # 控制台编码出错时用 replace，不中断运行
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(errors='replace')
        except Exception:
            pass
    logger.addHandler(console_handler)

    # 文件输出（10MB 轮转，最多保留 5 个文件）
    from src.config import LOG_DIR
    file_handler = RotatingFileHandler(
        LOG_DIR / "spider.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

"""
统一日志模块
基于 loguru，支持文件轮转和控制台美化输出
"""

import sys
from loguru import logger

from config.settings import settings


def setup_logger() -> None:
    """初始化日志配置"""
    logger.remove()  # 移除默认 handler

    # 控制台输出（带颜色）
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
        colorize=True,
    )

    # 文件输出（按天轮转，保留 30 天）
    log_file = settings.LOGS_DIR / "finpolicykg_{time:YYYY-MM-DD}.log"
    logger.add(
        str(log_file),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="00:00",
        retention="30 days",
        encoding="utf-8",
    )


# 模块级单例
setup_logger()

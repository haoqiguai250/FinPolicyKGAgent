"""
FinPolicyKG 全局配置
读取 .env 环境变量，提供统一配置入口
"""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局配置，自动从 .env 文件加载"""

    # ── 项目路径 ──
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    RAW_DIR: Path = DATA_DIR / "raw"
    PROCESSED_DIR: Path = DATA_DIR / "processed"
    TRIPLETS_DIR: Path = DATA_DIR / "triplets"
    RUN_LOGS_DIR: Path = DATA_DIR / "run_logs"
    LOGS_DIR: Path = BASE_DIR / "logs"

    # ── DeepSeek LLM ──
    DEEPSEEK_API_KEY: str = "your_api_key_here"
    DOUBAO_API_KEY: str = "your_api_key_here"  # 兼容旧字段（已废弃，保留以兼容.env）
    DOUBAO_BASE_URL: str = "https://api.deepseek.com"
    DOUBAO_MODEL: str = "deepseek-v4-flash"

    # ── 应用 ──
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# 全局单例
settings = Settings()


def ensure_dirs() -> None:
    """确保所有数据目录存在"""
    for d in [settings.RAW_DIR, settings.PROCESSED_DIR, settings.TRIPLETS_DIR, settings.RUN_LOGS_DIR, settings.LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

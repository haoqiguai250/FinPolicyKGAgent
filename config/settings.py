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
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"

    # ── Neo4j 图数据库 ──
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "finagent2026"
    NEO4J_DATABASE: str = "neo4j"

    # ── 应用 ──
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    PARALLEL_WORKERS: int = 6                 # 批量处理时的最大并行数
    CHUNK_PARALLEL_WORKERS: int = 6            # 单个文档内 chunk 最大并行数
    PERTURBATION_PARALLEL_WORKERS: int = 8     # 图扰动节点最大并行数

    # ── 爬虫 ──
    CRAWL_STATE_FILE: Path = DATA_DIR / "crawl_state.json"
    CRAWL_REPORTS_DIR: Path = DATA_DIR / "crawl_reports"
    CRAWL_REQUEST_TIMEOUT: int = 30        # 请求超时（秒）
    CRAWL_REQUEST_DELAY: float = 2.0       # 请求间隔（秒）
    CRAWL_MAX_LIST_PAGES: int = 5          # 每个列表页最多翻几页
    CRAWL_MAX_RETRIES: int = 3             # 最大重试次数
    CRAWL_KEYWORD_LAYERS: str = "core,industry"  # 默认关键词层

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# 全局单例
settings = Settings()


def ensure_dirs() -> None:
    """确保所有数据目录存在"""
    for d in [settings.RAW_DIR, settings.PROCESSED_DIR, settings.TRIPLETS_DIR, settings.RUN_LOGS_DIR, settings.LOGS_DIR, settings.CRAWL_REPORTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

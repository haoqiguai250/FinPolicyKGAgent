"""
FinPolicyKG 全局配置
读取 .env 环境变量，提供统一配置入口

目录规范（企业级）：
  data/            — 输入数据 + 中间产物（可重建）
  logs/            — 运行日志（调试用）
  outputs/         — 业务输出/交付物
"""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局配置，自动从 .env 文件加载"""

    # ── 项目路径 ──
    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    # data/ — 输入数据 + 中间产物
    DATA_DIR: Path = BASE_DIR / "data"
    RAW_DIR: Path = DATA_DIR / "raw"
    PROCESSED_DIR: Path = DATA_DIR / "processed"
    TRIPLETS_DIR: Path = DATA_DIR / "triplets"
    CRAWL_STATE_FILE: Path = DATA_DIR / "crawl" / "state.json"

    # logs/ — 运行日志
    LOGS_DIR: Path = BASE_DIR / "logs"                  # logs 总目录
    PIPELINE_LOGS_DIR: Path = BASE_DIR / "logs" / "pipeline"    # Pipeline 运行记录
    API_LOGS_DIR: Path = BASE_DIR / "logs" / "api"              # FastAPI 应用日志
    CRAWL_LOGS_DIR: Path = BASE_DIR / "logs" / "crawler"        # 爬虫运行日志

    # outputs/ — 业务输出/交付物
    REPORTS_DIR: Path = BASE_DIR / "outputs" / "reports"            # 批量汇总报告
    ADVISOR_RESULTS_DIR: Path = BASE_DIR / "outputs" / "advisor_results"  # 决策咨询结果
    EXPORTS_DIR: Path = BASE_DIR / "outputs" / "exports"            # KG 导出文件

    # ── LLM 提供商选择 ──
    LLM_PROVIDER: str = "deepseek"  # deepseek | openai | mimo
    
    # ── DeepSeek LLM ──
    DEEPSEEK_API_KEY: str = "your_api_key_here"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"
    
    # ── OpenAI LLM ──
    OPENAI_API_KEY: str = "your_openai_key_here"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o"
    
    # ── MiMo LLM (Xiaomi) ──
    MIMO_API_KEY: str = "your_mimo_key_here"
    MIMO_BASE_URL: str = "https://token-plan-cn.xiaomimimo.com/v1"
    MIMO_MODEL: str = "mimo-v2.5-pro"

    # ── Neo4j 图数据库 ──
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "finagent2026"
    NEO4J_DATABASE: str = "neo4j"

    # ── 应用 ──
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    PARALLEL_WORKERS: int = 16                # 批量处理时的最大并行数（支持更多PDF同时处理）
    CHUNK_PARALLEL_WORKERS: int = 64          # 单个文档内 chunk 最大并行数（大文档58+ chunks 一轮跑完）
    PERTURBATION_PARALLEL_WORKERS: int = 256   # 图扰动节点最大并行数
    MAX_PERTURBATION_NODES: int = 0           # 0 = 不采样，扰动全部节点

    # ── 爬虫 ──
    CRAWL_REQUEST_TIMEOUT: int = 30        # 请求超时（秒）
    CRAWL_REQUEST_DELAY: float = 2.0       # 请求间隔（秒）
    CRAWL_MAX_LIST_PAGES: int = 5          # 每个列表页最多翻几页
    CRAWL_MAX_RETRIES: int = 3             # 最大重试次数
    CRAWL_KEYWORD_LAYERS: str = "core,industry"  # 默认关键词层

    # ── 推送 ──
    ENTERPRISE_PROFILE_FILE: Path = BASE_DIR / "config" / "enterprise_profile.json"  # 企业画像
    PUSH_DIR: Path = BASE_DIR / "outputs" / "push"          # 推送报告
    PUSH_LOG_NO_MATCH: bool = True                           # 无匹配时是否写推送记录（预留开关）

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# 全局单例
settings = Settings()


def ensure_dirs() -> None:
    """确保所有数据目录存在"""
    dirs = [
        # data/
        settings.RAW_DIR,
        settings.PROCESSED_DIR,
        settings.TRIPLETS_DIR,
        settings.CRAWL_STATE_FILE.parent,
        # logs/
        settings.LOGS_DIR,
        settings.PIPELINE_LOGS_DIR,
        settings.API_LOGS_DIR,
        settings.CRAWL_LOGS_DIR,
        # outputs/
        settings.REPORTS_DIR,
        settings.ADVISOR_RESULTS_DIR,
        settings.EXPORTS_DIR,
        # outputs/push/
        settings.PUSH_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

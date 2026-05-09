"""
低空经济政策采集器（API 搜索模式）
通过深圳政策文件库 API 搜索国家/省/市/区四级政策，下载 PDF
"""

from src.ingestion.crawler.policy_source import ApiSearchConfig, API_SEARCH_TASKS, KEYWORDS, PolicySource
from src.ingestion.crawler.dedup import DedupManager
from src.ingestion.crawler.shenzhen_crawler import PolicyCrawler
from src.ingestion.crawler.scheduler import CrawlScheduler

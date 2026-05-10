"""
爬虫调度器（API 搜索模式）
1. 通过深圳政策文件库 API 搜索政策
2. 下载全部 PDF
3. 统一批量触发 Pipeline

用法:
    # 全量搜索 + 下载 + 批量跑 Pipeline
    python -m src.ingestion.crawler.scheduler --run

    # 只搜索下载，不跑 Pipeline
    python -m src.ingestion.crawler.scheduler --crawl-only

    # 只跑 Pipeline（处理 data/raw/ 中已有但未入库的文件）
    python -m src.ingestion.crawler.scheduler --pipeline-only

    # 查看状态
    python -m src.ingestion.crawler.scheduler --status
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from loguru import logger

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from config.settings import settings, ensure_dirs
from src.ingestion.crawler.policy_source import (
    get_enabled_search_tasks, get_search_tasks_by_level, get_keywords, KEYWORDS,
    ApiSearchConfig, API_SEARCH_TASKS,
)
from src.ingestion.crawler.dedup import DedupManager
from src.ingestion.crawler.shenzhen_crawler import PolicyCrawler


class CrawlScheduler:
    """爬虫调度器"""

    def __init__(
        self,
        keyword_layers: list[str] | None = None,
        max_api_pages: int = 10,
        request_delay: float = 1.5,
        levels: list[str] | None = None,
    ):
        """
        Args:
            keyword_layers: 关键词层，默认 ["core", "industry"]
            max_api_pages: 每个关键词最多翻几页 API
            request_delay: 请求间隔秒数
            levels: 要搜索的层级，默认全部 ["national", "provincial", "municipal", "district"]
        """
        self.keyword_layers = keyword_layers or ["core", "industry"]
        self.max_api_pages = max_api_pages
        self.request_delay = request_delay
        self.levels = levels

        self.dedup = DedupManager()
        self.crawler = PolicyCrawler(
            dedup_manager=self.dedup,
            keyword_layers=self.keyword_layers,
            max_api_pages=self.max_api_pages,
            request_delay=self.request_delay,
        )

    def run_crawl(self) -> list[dict]:
        """
        执行爬取（增量）

        Returns:
            爬取结果列表
        """
        ensure_dirs()
        logger.info("=" * 60)
        logger.info("低空经济政策采集器 启动 (API 搜索模式)")
        logger.info(f"关键词层: {self.keyword_layers}")
        logger.info(f"关键词数: {len(get_keywords(self.keyword_layers))}")
        logger.info(f"最多翻页: {self.max_api_pages}")
        logger.info("=" * 60)

        # 获取搜索任务
        if self.levels:
            sources = []
            for level in self.levels:
                sources.extend(get_search_tasks_by_level(level))
        else:
            sources = get_enabled_search_tasks()

        logger.info(f"启用的搜索任务: {len(sources)} 个")

        # 执行爬取
        start_time = datetime.now()
        results = self.crawler.crawl_all(sources)
        elapsed = (datetime.now() - start_time).total_seconds()

        # 统计
        downloaded = [r for r in results if r.status == "downloaded"]
        skipped = [r for r in results if r.status == "skipped"]
        failed = [r for r in results if r.status == "failed"]

        logger.info("=" * 60)
        logger.info(f"爬取完成！耗时: {elapsed:.1f}s")
        logger.info(f"  新下载: {len(downloaded)}")
        logger.info(f"  跳过: {len(skipped)}")
        logger.info(f"  失败: {len(failed)}")
        logger.info("=" * 60)

        # 保存去重状态
        self.dedup.update_last_crawl_time()
        self.dedup.save_state()

        # 保存爬取报告
        report = self._save_report(results, elapsed)
        logger.info(f"爬取报告: {report}")

        return [r.to_dict() for r in results]

    def run_pipeline(self):
        """统一批量触发 Pipeline"""
        from src.api.main import run_pipeline

        # 扫描 data/raw/ 中的 PDF
        raw_dir = settings.RAW_DIR
        pdf_files = sorted(raw_dir.glob("*.pdf"))

        if not pdf_files:
            logger.info("data/raw/ 中无 PDF 文件，跳过 Pipeline")
            return

        logger.info(f"开始批量 Pipeline: {len(pdf_files)} 个 PDF")

        for i, pdf_file in enumerate(pdf_files, 1):
            logger.info(f"[{i}/{len(pdf_files)}] 处理: {pdf_file.name}")
            try:
                result = run_pipeline(pdf_file)
                logger.info(f"  完成: 实体 {result.get('entities', '?')} 三元组 {result.get('triples', '?')}")
            except Exception as e:
                logger.error(f"  失败: {pdf_file.name} - {e}")

        logger.info("批量 Pipeline 完成")

    def run_full(self):
        """全流程：爬取 → 下载 → 批量 Pipeline"""
        results = self.run_crawl()

        # 检查是否有新下载的文件
        downloaded = [r for r in results if r.get("status") == "downloaded"]
        if downloaded:
            logger.info(f"新下载 {len(downloaded)} 个 PDF，开始批量 Pipeline...")
            self.run_pipeline()
        else:
            logger.info("无新下载的 PDF，跳过 Pipeline")

    def show_status(self):
        """显示当前爬取状态"""
        stats = self.dedup.get_stats()
        keywords = get_keywords(self.keyword_layers)
        tasks = get_enabled_search_tasks()

        print("=" * 60)
        print("低空经济政策采集器 状态 (API 搜索模式)")
        print("=" * 60)
        print(f"上次爬取时间: {stats['last_crawl_time'] or '从未爬取'}")
        print(f"已下载 URL 数: {stats['total_urls']}")
        print(f"已记录标题数: {stats['total_titles']}")
        print(f"内容指纹数: {stats['total_content_md5']}")
        print(f"关键词数: {len(keywords)} (层: {self.keyword_layers})")
        print(f"启用的搜索任务: {len(tasks)} 个")
        print()

        # 按层级统计
        for level in ["national", "provincial", "municipal", "district"]:
            level_tasks = get_search_tasks_by_level(level)
            level_names = [t.name for t in level_tasks]
            print(f"  {level}: {len(level_tasks)} 个 - {', '.join(level_names)}")

        print()
        print(f"RAW 目录: {settings.RAW_DIR}")
        raw_pdfs = list(settings.RAW_DIR.glob("*.pdf"))
        print(f"已有 PDF: {len(raw_pdfs)} 个")

        print("=" * 60)

    def _save_report(self, results: list, elapsed: float) -> Path:
        """保存爬取报告"""
        import json

        report_dir = settings.CRAWL_LOGS_DIR
        report_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = report_dir / f"crawl_{timestamp}.json"

        downloaded = [r for r in results if r.status == "downloaded"]
        skipped = [r for r in results if r.status == "skipped"]
        failed = [r for r in results if r.status == "failed"]

        report = {
            "timestamp": timestamp,
            "elapsed_seconds": round(elapsed, 1),
            "keyword_layers": self.keyword_layers,
            "total": len(results),
            "downloaded": len(downloaded),
            "skipped": len(skipped),
            "failed": len(failed),
            "results": [r.to_dict() for r in results],
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report_path


def main():
    """CLI 入口"""
    ensure_dirs()

    parser = argparse.ArgumentParser(description="低空经济政策采集器")
    parser.add_argument("--run", action="store_true", help="全流程：爬取 + 下载 + 批量 Pipeline")
    parser.add_argument("--crawl-only", action="store_true", help="只爬取下载，不跑 Pipeline")
    parser.add_argument("--pipeline-only", action="store_true", help="只跑 Pipeline（处理已有 PDF）")
    parser.add_argument("--status", action="store_true", help="查看爬取状态")
    parser.add_argument("--levels", type=str, default=None, help="搜索层级，逗号分隔: national,provincial,municipal,district")
    parser.add_argument("--keyword-layers", type=str, default=None, help="关键词层，逗号分隔: core,industry,support,department")
    parser.add_argument("--max-pages", type=int, default=10, help="每个关键词最多翻几页 API（默认 10）")
    parser.add_argument("--delay", type=float, default=1.5, help="请求间隔秒数（默认 1.5）")
    args = parser.parse_args()

    # 解析参数
    levels = args.levels.split(",") if args.levels else None
    keyword_layers = args.keyword_layers.split(",") if args.keyword_layers else None

    scheduler = CrawlScheduler(
        keyword_layers=keyword_layers,
        max_api_pages=args.max_pages,
        request_delay=args.delay,
        levels=levels,
    )

    if args.status:
        scheduler.show_status()
    elif args.crawl_only:
        scheduler.run_crawl()
    elif args.pipeline_only:
        scheduler.run_pipeline()
    elif args.run:
        scheduler.run_full()
    else:
        print("请指定操作：--run / --crawl-only / --pipeline-only / --status")
        print("示例: python -m src.ingestion.crawler.scheduler --run")
        print("      python -m src.ingestion.crawler.scheduler --crawl-only --levels municipal,district")
        print("      python -m src.ingestion.crawler.scheduler --status")


if __name__ == "__main__":
    main()

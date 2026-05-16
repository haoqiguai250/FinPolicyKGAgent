"""
政策推送调度器
1. 读取企业画像 → 自动构造查询
2. 调 Advisor 推理 → 检查匹配政策
3. 写推送报告（outputs/push/）

用法:
    # 手动触发推送
    python -m src.ingestion.crawler.push_scheduler --run

    # 先爬取再推送
    python -m src.ingestion.crawler.push_scheduler --run --crawl-first

    # 查看推送状态
    python -m src.ingestion.crawler.push_scheduler --status
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from config.settings import settings, ensure_dirs
from src.ingestion.crawler.dedup import DedupManager


class EnterpriseProfile:
    """企业画像"""

    def __init__(
        self,
        region: str = "",
        company_type: str = "",
        industry: str = "",
        extra_note: str = "",
    ):
        self.region = region
        self.company_type = company_type
        self.industry = industry
        self.extra_note = extra_note

    def to_query(self) -> str:
        """自动拼成 Advisor 查询问题"""
        parts = [p for p in [self.region, self.company_type, self.industry] if p]
        if not parts:
            return "能享受什么政策补贴？"
        return f"{' '.join(parts)} 能享受什么政策补贴？"

    def to_dict(self) -> dict:
        return {
            "region": self.region,
            "company_type": self.company_type,
            "industry": self.industry,
            "extra_note": self.extra_note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EnterpriseProfile":
        return cls(
            region=data.get("region", ""),
            company_type=data.get("company_type", ""),
            industry=data.get("industry", ""),
            extra_note=data.get("extra_note", ""),
        )

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "EnterpriseProfile":
        """从 JSON 文件加载企业画像"""
        path = path or settings.ENTERPRISE_PROFILE_FILE
        if not path.exists():
            logger.warning(f"企业画像文件不存在: {path}，使用空画像")
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile = cls.from_dict(data)
        logger.info(f"加载企业画像: {profile.to_query()}")
        return profile


class PushResult:
    """单次推送结果"""

    def __init__(
        self,
        push_time: str,
        profile: EnterpriseProfile,
        query: str,
        has_match: bool = False,
        matched_policies: Optional[list] = None,
        kg_rag_answer: str = "",
        llm_direct_answer: str = "",
        source: str = "",
        reasoning_paths: Optional[list] = None,
        new_policies_count: int = 0,
    ):
        self.push_time = push_time
        self.profile = profile
        self.query = query
        self.has_match = has_match
        self.matched_policies = matched_policies or []
        self.kg_rag_answer = kg_rag_answer
        self.llm_direct_answer = llm_direct_answer
        self.source = source
        self.reasoning_paths = reasoning_paths or []
        self.new_policies_count = new_policies_count

    def to_dict(self) -> dict:
        return {
            "push_time": self.push_time,
            "profile": self.profile.to_dict(),
            "query": self.query,
            "has_match": self.has_match,
            "matched_policies": self.matched_policies,
            "kg_rag_answer": self.kg_rag_answer,
            "llm_direct_answer": self.llm_direct_answer,
            "source": self.source,
            "reasoning_paths": self.reasoning_paths,
            "new_policies_count": self.new_policies_count,
        }

    def to_summary(self) -> str:
        """人类可读的推送摘要"""
        lines = [
            f"📅 推送时间: {self.push_time}",
            f"🏢 企业画像: {self.profile.to_query()}",
            f"🔍 查询问题: {self.query}",
        ]
        if self.has_match:
            lines.append(f"✅ 匹配到 {len(self.matched_policies)} 条政策")
            lines.append(f"📋 KG-RAG 建议: {self.kg_rag_answer[:200]}...")
        else:
            lines.append("📭 今日无新匹配政策")
        return "\n".join(lines)


class PushScheduler:
    """政策推送调度器"""

    def __init__(self, fast_mode: bool = True):
        """
        Args:
            fast_mode: 推送时是否使用快速模式（跳过扰动分析，默认 True）
        """
        self.fast_mode = fast_mode
        self.dedup = DedupManager()

    def run_push(self, crawl_first: bool = False, max_tasks: Optional[int] = None) -> PushResult:
        """
        执行推送

        Args:
            crawl_first: 是否先跑一轮爬虫再推送
            max_tasks: 测试用，限制爬虫搜索任务数（默认全部）

        Returns:
            PushResult
        """
        ensure_dirs()
        push_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        logger.info("=" * 60)
        logger.info("政策推送 启动")
        logger.info("=" * 60)

        # 1. 如果需要，先爬取 + 抽取
        new_count = 0
        source_files: list[str] = []
        if crawl_first:
            new_count = self._run_crawl(max_tasks=max_tasks)
            source_files = self._run_pipeline()  # 返回新下载的 PDF 路径

        # 如果没有新政策，跳过推送
        if not source_files:
            logger.info("没有新政策，跳过推送")
            return PushResult(
                push_time=push_time,
                profile=EnterpriseProfile.load(),
                query="",
                has_match=False,
            )

        # 2. 读取企业画像
        profile = EnterpriseProfile.load()
        query = profile.to_query()

        if not query or query == "能享受什么政策补贴？":
            logger.warning("企业画像为空，无法生成查询，跳过推送")
            return PushResult(
                push_time=push_time,
                profile=profile,
                query=query,
                has_match=False,
            )

        logger.info(f"推送查询: {query}" + f"（限 {len(source_files)} 个新政策）")

        # 3. 调 Advisor 推理（只查新政策）
        try:
            advisor_result = self._run_advisor(query, source_files=source_files)
        except Exception as e:
            logger.error(f"Advisor 推理失败: {e}")
            return PushResult(
                push_time=push_time,
                profile=profile,
                query=query,
                has_match=False,
            )

        # 4. 判断匹配结果
        matched_policies = []
        kg_rag_answer = ""
        llm_direct_answer = ""
        source = ""
        reasoning_paths = []

        if advisor_result:
            matched_policies = [
                p.get("policy_name", str(p)) if isinstance(p, dict) else str(p)
                for p in (advisor_result.get("matched_policies") or [])
            ]
            kg_rag_answer = advisor_result.get("kg_rag_answer", "")
            llm_direct_answer = advisor_result.get("llm_direct_answer", "")
            source = advisor_result.get("source", "")
            reasoning_paths = advisor_result.get("reasoning_paths", [])

        has_match = len(matched_policies) > 0

        # 推送场景：无匹配时 KG-RAG 替换为模板，LLM 直接回答仍保留
        if not has_match:
            profile_parts = [p for p in [profile.region, profile.company_type, profile.industry] if p]
            if profile_parts:
                no_match_msg = f"本次未找到与【{'·'.join(profile_parts)}】匹配的新政策，将持续为您关注。"
            else:
                no_match_msg = "本次未找到匹配的新政策，将持续为您关注。"
            kg_rag_answer = no_match_msg

        # 5. 构建推送结果
        result = PushResult(
            push_time=push_time,
            profile=profile,
            query=query,
            has_match=has_match,
            matched_policies=matched_policies,
            kg_rag_answer=kg_rag_answer,
            llm_direct_answer=llm_direct_answer,
            source=source,
            reasoning_paths=reasoning_paths,
            new_policies_count=new_count,
        )

        # 6. 写推送报告
        self._save_push_report(result)

        # 7. 终端输出
        print(result.to_summary())

        logger.info("=" * 60)
        logger.info(f"推送完成: {'有匹配' if has_match else '无匹配'}")
        logger.info("=" * 60)

        return result

    def _run_crawl(self, max_tasks: Optional[int] = None) -> int:
        """跑一轮爬虫，返回新下载的 PDF 数

        Args:
            max_tasks: 测试用，限制最多跑几个搜索任务（默认全部）
        """
        from src.ingestion.crawler.scheduler import CrawlScheduler

        logger.info("先执行爬取..." + (f" [测试模式: 限制 {max_tasks} 个任务]" if max_tasks else ""))
        scheduler = CrawlScheduler()
        # 测试模式：max_tasks 同时作为 max_pdfs（限制搜索任务数 + PDF 下载数）
        results = scheduler.run_crawl(max_tasks=max_tasks, max_pdfs=max_tasks or 0)
        self._last_crawl_results = results
        new_count = len([r for r in results if r.get("status") == "downloaded"])
        logger.info(f"爬取完成: 新下载 {new_count} 个 PDF")
        return new_count

    def _run_pipeline(self) -> list[str]:
        """运行抽取 Pipeline（解析 → 分块 → 抽取 → 存储）"""
        from pathlib import Path
        from src.api.main import run_pipeline  # 导入抽取 Pipeline 主函数

        # 获取爬取结果中新下载的 PDF 列表
        source_paths = [
            r["pdf_path"]
            for r in self._last_crawl_results
            if r.get("status") == "downloaded" and r.get("pdf_path")
        ]

        if not source_paths:
            logger.warning("没有新下载的 PDF，跳过抽取")
            return []

        new_pdfs = [Path(p) for p in source_paths]

        logger.info(f"开始抽取 Pipeline，共 {len(new_pdfs)} 个新 PDF...")

        for pdf_file in new_pdfs:
            try:
                logger.info(f"正在抽取: {pdf_file.name}")
                run_pipeline(pdf_file, reflect=False)
                logger.info(f"抽取完成: {pdf_file.name}")
            except Exception as e:
                logger.error(f"抽取失败 {pdf_file.name}: {e}")

        return source_paths  # 返回 PDF 路径，供 Advisor 按来源过滤

    def _run_advisor(self, query: str, source_files: list[str] = None) -> Optional[dict]:
        """调用 Advisor 推理"""
        from src.decision.advisor import Advisor
        from src.storage.neo4j_store import Neo4jStore
        from src.extraction.llm_client import get_reasoning_llm_client

        # 优先使用 Neo4j 后端
        neo4j_store = None
        try:
            neo4j_store = Neo4jStore(
                uri=settings.NEO4J_URI,
                user=settings.NEO4J_USER,
                password=settings.NEO4J_PASSWORD,
                database=settings.NEO4J_DATABASE,
            )
            logger.info("Neo4j 后端已连接")
        except Exception as e:
            logger.warning(f"Neo4j 连接失败: {e}，无法执行推送（推送需要 Neo4j 后端）")
            return None

        advisor = Advisor(
            neo4j_store=neo4j_store,
            enable_explanation=not self.fast_mode,  # 快速模式跳过扰动
        )
        advisor_result = advisor.advise(query, fast_mode=self.fast_mode, source_files=source_files)
        return advisor_result.to_dict()

    def _save_push_report(self, result: PushResult) -> Optional[Path]:
        """保存推送报告"""
        # 无匹配且开关关闭时不写记录
        if not result.has_match and not settings.PUSH_LOG_NO_MATCH:
            logger.info("无匹配且 PUSH_LOG_NO_MATCH=False，跳过写推送记录")
            return None

        push_dir = settings.PUSH_DIR
        push_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now().strftime("%Y%m%d")
        report_path = push_dir / f"push_{date_str}.json"

        # 如果当天已有推送记录，追加而非覆盖
        existing = []
        if report_path.exists():
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if not isinstance(existing, list):
                    existing = [existing]
            except Exception:
                existing = []

        existing.append(result.to_dict())

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        logger.info(f"推送报告已保存: {report_path}")
        return report_path

    def show_status(self):
        """显示推送状态"""
        profile = EnterpriseProfile.load()
        dedup_stats = self.dedup.get_stats()

        print("=" * 60)
        print("政策推送 状态")
        print("=" * 60)
        print(f"企业画像: {profile.to_query()}")
        print(f"画像文件: {settings.ENTERPRISE_PROFILE_FILE}")
        print(f"推送目录: {settings.PUSH_DIR}")
        print(f"上次爬取: {dedup_stats['last_crawl_time'] or '从未爬取'}")
        print(f"无匹配写记录: {'是' if settings.PUSH_LOG_NO_MATCH else '否'}")
        print()

        # 推送历史
        push_dir = settings.PUSH_DIR
        if push_dir.exists():
            reports = sorted(push_dir.glob("push_*.json"))
            print(f"推送记录: {len(reports)} 天")
            for report in reports[-5:]:  # 最近 5 天
                try:
                    with open(report, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        matches = sum(1 for r in data if r.get("has_match"))
                        print(f"  {report.stem}: {len(data)} 次推送, {matches} 次有匹配")
                    else:
                        print(f"  {report.stem}: 1 次推送")
                except Exception:
                    print(f"  {report.stem}: 读取失败")

        print("=" * 60)


def main():
    """CLI 入口"""
    ensure_dirs()

    parser = argparse.ArgumentParser(description="政策推送调度器")
    parser.add_argument("--run", action="store_true", help="执行推送（用企业画像查询匹配政策）")
    parser.add_argument("--crawl-first", action="store_true", help="推送前先跑一轮爬虫")
    parser.add_argument("--status", action="store_true", help="查看推送状态")
    parser.add_argument("--full", action="store_true", help="全流程：爬取 + 推送")
    parser.add_argument("--no-fast", action="store_true", help="关闭快速模式（跑扰动分析）")
    parser.add_argument("--test", action="store_true", help="测试模式：爬虫只跑 1 个搜索任务（避免大量下载）")
    args = parser.parse_args()

    # 测试模式 → 限制爬虫最多 1 个任务
    max_tasks = 1 if args.test else None

    scheduler = PushScheduler(fast_mode=not args.no_fast)

    if args.status:
        scheduler.show_status()
    elif args.run:
        scheduler.run_push(crawl_first=args.crawl_first, max_tasks=max_tasks)
    elif args.full:
        scheduler.run_push(crawl_first=True, max_tasks=max_tasks)
    else:
        print("请指定操作：--run / --full / --status")
        print("示例:")
        print("  python -m src.ingestion.crawler.push_scheduler --run          # 手动推送")
        print("  python -m src.ingestion.crawler.push_scheduler --full         # 爬取+推送")
        print("  python -m src.ingestion.crawler.push_scheduler --status       # 查看状态")
        print("  python -m src.ingestion.crawler.push_scheduler --full --test  # 测试模式（只爬1个任务）")


if __name__ == "__main__":
    main()

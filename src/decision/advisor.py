"""
决策支持总入口 — Advisor

完整流程：
1. IntentRecognizer: 自然语言 → 企业画像
2. GraphRetriever: 企业画像 → 图遍历 → 推理路径
3. PathToTextConverter: 推理路径 → 虚拟段落
4. RAGGenerator: 虚拟段落 + 问题 → 个性化建议
5. Perturbator: 节点扰动 → 重要性推断
6. ExplanationGenerator: 扰动报告 → 结构化解释

双输出：
- 个性化政策建议
- 可解释性分析

每次运行自动保存完整 JSON 产物到 outputs/advisor_results/
包含：推理子图、扰动过滤后子图、各节点评分、三次 LLM 回答

存储后端：
- Neo4j（推荐）：Cypher 路径查询 + DETACH DELETE 扰动
- JSON（兼容）：内存索引 + 深拷贝扰动
"""

import argparse
import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from loguru import logger

from src.extraction.llm_client import get_reasoning_llm_client
from src.storage.triplet_store import TripletStore
from src.storage.neo4j_store import Neo4jStore
from src.decision.intent_recognizer import IntentRecognizer, EnterpriseProfile
from src.decision.graph_retriever import GraphRetriever, RetrievalResult
from src.decision.path_to_text import PathToTextConverter
from src.decision.rag_generator import RAGGenerator, RAGResult
from src.decision.perturbator import Perturbator, PerturbationReport
from src.decision.explanation_generator import ExplanationGenerator, Explanation
from config.settings import settings


@dataclass
class AdvisorResult:
    """决策支持完整结果"""
    query: str
    profile: EnterpriseProfile
    retrieval: RetrievalResult
    context: str
    rag_result: RAGResult
    # ── LLM 直接生成结果（始终并行产出） ──
    llm_direct_result: RAGResult
    # ── 来源标记：kg_rag / llm_direct / both ──
    source: str = "both"
    perturbation_report: Optional[PerturbationReport] = None
    explanation: Optional[Explanation] = None

    # ── 保留所有阶段产物（低分节点过滤前后完整保留） ──
    original_kg_rag_answer: str = ""            # 首次 KG-RAG 回答（过滤前）
    filtered_kg_rag_answer: Optional[str] = None  # 过滤低分节点后重新生成的回答
    original_paths: list = field(default_factory=list)      # 原始推理路径（to_dict 格式）
    filtered_paths: Optional[list] = None        # 过滤后的推理路径（to_dict 格式）
    low_score_nodes: list = field(default_factory=list)     # 被过滤的低分节点列表

    auto_save_path: Optional[str] = None         # 自动保存的文件路径

    def to_dict(self) -> dict:
        # ── 构建原始推理路径（含扰动评分） ──
        def _build_paths(paths, perturb_report):
            result = []
            for path in paths:
                entry = path.to_dict()
                if perturb_report:
                    entry["perturbation_scores"] = [
                        {
                            "node": p["node"],
                            "display": p["display"],
                            "importance": p["importance"],
                            "reason": p["reason"],
                            "source_chunk_id": p["source_chunk_id"],
                            "source_text": p["source_text"],
                            "metric_scores": p.get("metric_scores", {}),
                        }
                        for p in perturb_report.ranked_perturbations
                        if self._node_belongs_to(p, path)
                    ]
                result.append(entry)
            return result

        # ── 用 _build_paths 保证返回的路径都带 perturbation_scores ──
        reasoning_paths = _build_paths(self.retrieval.paths, self.perturbation_report)
        filtered_paths = reasoning_paths
        if self.filtered_paths is not None and self.perturbation_report:
            # 低分过滤后：将 perturbation_scores 附加到过滤后的路径 dict 上
            for entry in self.filtered_paths:
                entry["perturbation_scores"] = [
                    {
                        "node": p["node"],
                        "display": p["display"],
                        "importance": p["importance"],
                        "reason": p["reason"],
                        "source_chunk_id": p["source_chunk_id"],
                        "source_text": p["source_text"],
                        "metric_scores": p.get("metric_scores", {}),
                    }
                    for p in self.perturbation_report.ranked_perturbations
                    if self._node_belongs_to_dict(p, entry)
                ]
            filtered_paths = self.filtered_paths

        return {
            "query": self.query,
            "profile": self.profile.to_dict(),
            "source": self.source,
            "auto_save_path": self.auto_save_path,

            # ── 三次 LLM 回答 ──
            "original_kg_rag_answer": self.original_kg_rag_answer,    # 首次 KG-RAG 回答
            "filtered_kg_rag_answer": self.filtered_kg_rag_answer,    # 过滤后重新生成
            "llm_direct_answer": self.llm_direct_result.answer,      # 直接问 LLM

            # ── 推理子图 ──
            "original_paths": reasoning_paths,                         # 过滤前完整子图（带分数）
            "filtered_paths": filtered_paths,                          # 过滤后子图（带分数）
            "low_score_nodes": self.low_score_nodes,                   # 被删除的低分节点

            # ── 汇总统计 ──
            "matched_policies": self.retrieval.matched_policies,
            "matched_actions": self.retrieval.matched_actions,
            "matched_strategies": self.retrieval.matched_strategies,
            "explanation": self.explanation.to_dict() if self.explanation else None,
        }

    @staticmethod
    def _node_belongs_to(perturbed_node: dict, path: 'ReasoningPath') -> bool:
        """判断一个扰动节点是否属于某条 ReasoningPath"""
        node_info = perturbed_node.get("node", {})
        name = node_info.get("name", "")
        node_type = node_info.get("type", "")

        if node_type == "Policy":
            return path.policy_name == name
        elif node_type == "Condition":
            return any(c.get("value") == name for c in path.conditions)
        elif node_type == "ActionType":
            return path.action_type == name
        elif node_type == "Strategy":
            return name in path.strategies
        return False

    @staticmethod
    def _node_belongs_to_dict(perturbed_node: dict, path_dict: dict) -> bool:
        """判断一个扰动节点是否属于某条路径 dict（用于过滤后路径）"""
        node_info = perturbed_node.get("node", {})
        name = node_info.get("name", "")
        node_type = node_info.get("type", "")

        if node_type == "Policy":
            return path_dict.get("policy") == name
        elif node_type == "Condition":
            return any(c.get("value") == name for c in path_dict.get("conditions", []))
        elif node_type == "ActionType":
            return path_dict.get("action_type") == name
        elif node_type == "Strategy":
            return name in path_dict.get("strategies", [])
        return False

    def to_summary(self) -> str:
        """生成人类可读的摘要"""
        lines = [
            f"📋 企业画像: {self._format_profile()}",
            f"",
        ]

        # ── KG-RAG 结果 ──
        if self.retrieval.paths:
            lines.append(f"💡 【KG-RAG 流程结果】(基于知识图谱推理)")
            lines.append(self.rag_result.answer)
            lines.append(f"")
            lines.append(f"📊 匹配概况:")
            lines.append(f"  - 政策: {', '.join(self.retrieval.matched_policies) or '无'}")
            lines.append(f"  - 措施: {', '.join(self.retrieval.matched_actions) or '无'}")
            lines.append(f"  - 策略: {', '.join(self.retrieval.matched_strategies) or '无'}")
        else:
            lines.append(f"⚠️ 【KG-RAG 流程结果】未匹配到相关政策")

        # ── LLM 直接结果 ──
        lines.append(f"")
        lines.append(f"🤖 【LLM 直接生成】(无知识图谱支撑，仅供参考)")
        lines.append(self.llm_direct_result.answer)

        # ── 解释分析 ──
        if self.explanation:
            lines.append(f"")
            lines.append(f"🔍 解释分析:")
            lines.append(self.explanation.summary)
            if self.explanation.detail_text:
                lines.append(self.explanation.detail_text)

        return "\n".join(lines)

    def _format_profile(self) -> str:
        parts = []
        if self.profile.region:
            parts.append(self.profile.region)
        if self.profile.company_type:
            parts.append(self.profile.company_type)
        if self.profile.industry:
            parts.append(self.profile.industry)
        return " | ".join(parts) if parts else "未指定"


class Advisor:
    """决策支持总入口

    支持两种存储后端：
    - Neo4jStore: Cypher 查询 + DETACH DELETE 扰动（推荐）
    - TripletStore: 内存索引 + 深拷贝扰动（兼容旧数据）
    """

    def __init__(
        self,
        store: Optional[TripletStore] = None,
        store_path: Optional[Path] = None,
        neo4j_store: Optional[Neo4jStore] = None,
        llm_client=None,
        enable_explanation: bool = True,
    ):
        """
        Args:
            store: 已加载的 TripletStore（JSON 后端）
            store_path: KG JSON 文件路径（JSON 后端）
            neo4j_store: 已连接的 Neo4jStore（Neo4j 后端，优先使用）
            llm_client: LLM 客户端
            enable_explanation: 是否启用解释层（扰动分析较耗时）
        """
        self.llm = llm_client or get_reasoning_llm_client()
        self.enable_explanation = enable_explanation
        self.neo4j_store = neo4j_store

        # 确定传给 GraphRetriever 的后端
        if neo4j_store:
            retriever_store = neo4j_store
            retriever_path = None
        else:
            retriever_store = store
            retriever_path = store_path

        # 构建模块链
        self.intent_recognizer = IntentRecognizer(self.llm)
        self.retriever = GraphRetriever(store=retriever_store, store_path=retriever_path)
        self.converter = PathToTextConverter()
        self.generator = RAGGenerator(self.llm)
        self.perturbator = Perturbator(
            self.retriever, self.generator, self.converter,
            llm_client=self.llm,
        )
        self.explanation_generator = ExplanationGenerator()

    def advise(self, query: str, fast_mode: bool = False, source_files: list[str] = None) -> AdvisorResult:
        """
        执行完整决策支持流程（双路生成）

        始终同时产出两条路径的结果：
        1. KG-RAG 流程：意图识别 → 图检索 → 路径转文本 → RAG 生成（+ 可选扰动分析）
        2. LLM 直接生成：直接将用户问题丢给 LLM

        Args:
            query: 用户自然语言查询
            fast_mode: 是否启用快速模式（跳过扰动分析，提速 ~50-70%）
            source_files: 可选，限制只检索这些来源文件对应的政策（如新抓取的 PDF 路径）

        Returns:
            AdvisorResult（含 kg_rag + llm_direct 双输出，source 标注来源）
        """
        logger.info(f"开始决策支持: {query}，fast_mode={fast_mode}" + (f", source_files={len(source_files)} 个" if source_files else ""))

        # 1. 意图识别
        profile = self.intent_recognizer.recognize(query)

        # 2. 图检索
        retrieval = self.retriever.retrieve(profile, source_files=source_files)

        # 3. 路径转文本
        context = self.converter.convert(retrieval)

        # 4 & 5. 并行执行 RAG生成 + LLM直接生成（省 20+ 秒）
        logger.info("并行执行 KG-RAG 生成 + LLM 直接生成...")
        rag_result = None
        llm_direct_result = None
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(self.generator.generate, query, profile, context): "rag",
                executor.submit(self.generator.generate_direct, query, profile): "direct",
            }
            for future in as_completed(futures):
                label = futures[future]
                try:
                    if label == "rag":
                        rag_result = future.result()
                    else:
                        llm_direct_result = future.result()
                except Exception as e:
                    logger.error(f"{label} 生成失败: {e}")
        # 安全兜底
        if rag_result is None:
            rag_result = RAGResult(answer="", profile=profile, context_used="")
        if llm_direct_result is None:
            llm_direct_result = RAGResult(answer="", profile=profile, context_used="")

        # 6 & 7. 解释层（KG 匹配且非快速模式时触发扰动分析）
        perturbation_report = None
        explanation = None
        # ── 保存首次 KG-RAG 的原始产物（过滤前） ──
        original_rag_answer = rag_result.answer
        original_paths = [p.to_dict() for p in retrieval.paths]
        filtered_rag_answer = None
        filtered_paths_result = None
        low_score_nodes_result = []
        if (self.enable_explanation and not fast_mode) and retrieval.paths:
            perturbation_report = self.perturbator.analyze(
                query=query,
                profile=profile,
                original_result=retrieval,
                original_answer=original_rag_answer,
            )

            # ── 低分节点过滤：删除 importance < 0.2 的节点，重新生成答案 ──
            FILTER_THRESHOLD = 0.2
            if perturbation_report and perturbation_report.ranked_perturbations:
                low_score_nodes_result = [
                    p["node"] for p in perturbation_report.ranked_perturbations
                    if p["importance"] < FILTER_THRESHOLD
                ]
                if low_score_nodes_result:
                    logger.info(f"过滤低分节点 (importance < {FILTER_THRESHOLD}): {len(low_score_nodes_result)} 个")
                    filtered_paths = Advisor._filter_paths_by_nodes(retrieval.paths, low_score_nodes_result)
                    filtered_paths_result = [p.to_dict() for p in filtered_paths]
                    if filtered_paths and len(filtered_paths) < len(retrieval.paths):
                        # 重建 RetrievalResult
                        filtered_result = RetrievalResult(
                            profile=profile,
                            paths=filtered_paths,
                        )
                        filtered_result.matched_policies = sorted(set(p.policy_name for p in filtered_paths))
                        filtered_result.matched_actions = sorted(set(p.action_type for p in filtered_paths))
                        filtered_result.matched_strategies = sorted(
                            s for p in filtered_paths for s in p.strategies
                        )
                        # 重新生成 RAG 答案
                        filtered_context = self.converter.convert(filtered_result)
                        new_rag_result = self.generator.generate(query, profile, filtered_context)
                        filtered_rag_answer = new_rag_result.answer
                        rag_result = new_rag_result
                        logger.info(f"低分节点过滤后重新生成答案完成: {len(filtered_rag_answer)} 字符")
                    elif not filtered_paths:
                        logger.warning("低分节点过滤后无剩余路径，保留原始答案")

            explanation = self.explanation_generator.generate(perturbation_report)
        elif not retrieval.paths:
            # KG 未匹配时生成友好提示（快速模式也保留）
            available_policies = self._get_available_policies()
            explanation = self.explanation_generator.generate_no_match(available_policies)

        # 来源标记
        source = "both" if retrieval.paths else "llm_direct"

        # 无匹配时：KG-RAG 回答替换为模板说明，LLM 直接回答仍正常生成
        if not retrieval.paths:
            no_match_msg = f"当前未找到与【{query}】相关的政策。"
            rag_result = RAGResult(answer=no_match_msg, profile=profile, context_used="")
            original_rag_answer = no_match_msg  # 同步更新 to_dict 使用的原始字段

        result = AdvisorResult(
            query=query,
            profile=profile,
            retrieval=retrieval,
            context=context,
            rag_result=rag_result,
            llm_direct_result=llm_direct_result,
            source=source,
            perturbation_report=perturbation_report,
            explanation=explanation,
            # ── 保留各阶段产物 ──
            original_kg_rag_answer=original_rag_answer,
            filtered_kg_rag_answer=filtered_rag_answer,
            original_paths=original_paths,
            filtered_paths=filtered_paths_result,
            low_score_nodes=low_score_nodes_result,
        )

        # ── 自动保存完整 JSON 产物 ──
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
            save_dir = settings.ADVISOR_RESULTS_DIR
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / f"advise_{timestamp}_{query_hash}.json"
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
            result.auto_save_path = str(save_path)
            logger.info(f"决策结果已自动保存: {save_path}")
        except Exception as e:
            logger.warning(f"自动保存决策结果失败（不影响返回结果）: {e}")

        logger.info(
            f"决策支持完成: KG路径={len(retrieval.paths)}条, "
            f"来源={source}, 解释={'是' if explanation else '否'}"
        )
        return result

    def _get_available_policies(self) -> list[str]:
        """获取当前 KG 中已收录的政策列表（用于无匹配时的友好提示）"""
        policies = []
        try:
            if self.neo4j_store:
                from src.storage.cypher_queries import FIND_POLICIES_BY_CONDITIONS
                with self.neo4j_store.driver.session(database=self.neo4j_store.database) as session:
                    results = session.run(FIND_POLICIES_BY_CONDITIONS)
                    policies = [r["policy_name"] for r in results]
            elif self.retriever.store:
                # JSON 后端：从 policy_to_conditions 索引取
                policies = list(self.retriever.policy_to_conditions.keys())
        except Exception as e:
            logger.warning(f"获取已收录政策列表失败: {e}")
        return policies

    @staticmethod
    def _filter_paths_by_nodes(
        paths: list['ReasoningPath'],
        removed_nodes: list[dict],
    ) -> list['ReasoningPath']:
        """
        过滤掉包含任意低分节点的所有 ReasoningPath

        removed_nodes: list of dict, 每个 dict 含 "name" 和 "type" 字段
                     例如 [{"name": "某某政策", "type": "Policy"}, ...]
        """
        # 构建快速查找 set: {(name, type), ...}
        remove_set = {(n["name"], n["type"]) for n in removed_nodes}

        filtered = []
        for path in paths:
            # 检查该路径是否包含任何待删除节点
            should_remove = False

            # Policy 节点
            if ("Policy", path.policy_name) in remove_set:
                should_remove = True
            # Condition 节点
            for cond in path.conditions:
                val = cond.get("value", "")
                if val and ("Condition", val) in remove_set:
                    should_remove = True
                    break
            # ActionType 节点
            if not should_remove and ("ActionType", path.action_type) in remove_set:
                should_remove = True
            # Strategy 节点
            if not should_remove:
                for strat in path.strategies:
                    if strat and ("Strategy", strat) in remove_set:
                        should_remove = True
                        break

            if not should_remove:
                filtered.append(path)

        return filtered


# ── 独立运行入口 ──

def run_advise(
    query: str,
    store_path: Optional[str] = None,
    output_path: Optional[str] = None,
    use_neo4j: bool = False,
):
    """独立运行决策支持

    Args:
        query: 用户查询
        store_path: KG JSON 文件路径（JSON 后端时必填）
        output_path: 结果输出路径
        use_neo4j: 是否使用 Neo4j 后端
    """
    neo4j_store = None
    store = None
    path = None

    if use_neo4j:
        try:
            from config.settings import settings
            neo4j_store = Neo4jStore(
                uri=settings.NEO4J_URI,
                user=settings.NEO4J_USER,
                password=settings.NEO4J_PASSWORD,
                database=settings.NEO4J_DATABASE,
            )
            logger.info("Neo4j 后端已连接")
        except Exception as e:
            logger.error(f"Neo4j 连接失败，降级到 JSON: {e}")
            use_neo4j = False

    if not use_neo4j:
        if not store_path:
            logger.error("JSON 后端需指定 store_path")
            return
        path = Path(store_path)
        if not path.exists():
            logger.error(f"KG 文件不存在: {path}")
            return
        logger.info(f"JSON 后端: {path}")

    advisor = Advisor(store_path=path, neo4j_store=neo4j_store)
    result = advisor.advise(query)

    print(result.to_summary())

    # 自动保存已在 advise() 中完成，--output 作为额外备份路径
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"结果已额外保存到: {out}")

    if result.auto_save_path:
        print(f"\n完整 JSON 产物已自动保存到: {result.auto_save_path}")

    # 关闭 Neo4j 连接
    if neo4j_store:
        neo4j_store.close()

    return result


if __name__ == "__main__":
    import sys

    parser = argparse.ArgumentParser(description="FinPolicyKG 决策支持")
    parser.add_argument("query", help="查询语句")
    parser.add_argument("--store", help="KG JSON 文件路径（JSON 后端时必填）")
    parser.add_argument("--output", help="结果输出路径")
    parser.add_argument("--neo4j", action="store_true", help="使用 Neo4j 后端")

    args = parser.parse_args()

    if not args.neo4j and not args.store:
        parser.error("JSON 后端需指定 --store 参数，或使用 --neo4j")

    run_advise(
        query=args.query,
        store_path=args.store,
        output_path=args.output,
        use_neo4j=args.neo4j,
    )

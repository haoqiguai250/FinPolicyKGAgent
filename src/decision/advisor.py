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
from src.decision.eligibility_engine import EligibilityEngine, EligibilityResult
from src.decision.missing_detector import MissingInfoDetector, MissingInfoReport
from config.settings import settings


@dataclass
class ApplicationPlan:
    """单个政策的申报执行方案"""
    policy_name: str
    policy_id: str = ""
    is_eligible: bool = False
    eligibility_result: Optional[EligibilityResult] = None
    match_explanation: str = ""          # LLM 生成：为什么匹配
    suggestions: str = ""                # LLM 生成：申报建议
    # ── 结构化字段（从 KG 读取，不由 LLM 生成） ──
    required_materials: list[str] = field(default_factory=list)
    application_steps: list[str] = field(default_factory=list)
    deadline: str = ""
    platform_url: str = ""
    platform_name: str = ""
    source_department: str = ""
    policy_doc_id: str = ""
    estimated_amount: str = ""
    effective_date: str = ""           # 政策生效日期
    expiry_date: str = ""             # 政策失效日期
    policy_status: str = ""           # active / repealed / expiring_soon

    def to_dict(self) -> dict:
        d = {
            "policy_name": self.policy_name,
            "policy_id": self.policy_id,
            "is_eligible": self.is_eligible,
            "match_explanation": self.match_explanation,
            "suggestions": self.suggestions,
            "required_materials": self.required_materials,
            "application_steps": self.application_steps,
            "deadline": self.deadline,
            "platform_url": self.platform_url,
            "platform_name": self.platform_name,
            "source_department": self.source_department,
            "policy_doc_id": self.policy_doc_id,
            "estimated_amount": self.estimated_amount,
            "effective_date": self.effective_date,
            "expiry_date": self.expiry_date,
            "policy_status": self.policy_status,
        }
        if self.eligibility_result:
            d["eligibility_checks"] = self.eligibility_result.to_dict()
        return d


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

    # ── Phase 1 新增：申报执行方案 + 缺失信息 ──
    application_plans: list[ApplicationPlan] = field(default_factory=list)
    missing_info: Optional[MissingInfoReport] = None

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

            # ── Phase 1 新增：申报执行方案 + 缺失信息 ──
            "application_plans": [p.to_dict() for p in self.application_plans],
            "missing_info": self.missing_info.to_dict() if self.missing_info else None,
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

    def advise(self, query: str, fast_mode: bool = False, source_files: list[str] = None, profile: EnterpriseProfile = None, skip_rag: bool = False) -> AdvisorResult:
        """
        执行完整决策支持流程（双路生成）

        始终同时产出两条路径的结果：
        1. KG-RAG 流程：意图识别 → 图检索 → 路径转文本 → RAG 生成（+ 可选扰动分析）
        2. LLM 直接生成：直接将用户问题丢给 LLM

        Args:
            query: 用户自然语言查询
            fast_mode: 是否启用快速模式（跳过扰动分析，提速 ~50-70%）
            source_files: 可选，限制只检索这些来源文件对应的政策（如新抓取的 PDF 路径）
            profile: 可选，预构建的企业画像。若提供则跳过 LLM 意图识别
            skip_rag: 跳过 RAG 长文生成+解释层，只保留条件核验+申报计划（工作台专用，提速 ~60%）

        Returns:
            AdvisorResult（含 kg_rag + llm_direct 双输出，source 标注来源）
        """
        logger.info(f"开始决策支持: {query}，fast_mode={fast_mode}" + (f", source_files={len(source_files)} 个" if source_files else ""))

        # 1. 意图识别 — 若有预构建画像则跳过 LLM 调用
        if profile is not None:
            logger.info(f"跳过 LLM 意图识别，使用预构建画像: {profile.to_dict()}")
        else:
            profile = self.intent_recognizer.recognize(query)

        # 2. 图检索
        retrieval = self.retriever.retrieve(profile, source_files=source_files)

        # 3. 路径转文本
        context = self.converter.convert(retrieval)

        # 4 & 5. 并行执行 RAG生成 + LLM直接生成（skip_rag 时跳过，省 50%+ 时间）
        rag_result = None
        llm_direct_result = None
        if not skip_rag:
            logger.info("并行执行 KG-RAG 生成 + LLM 直接生成...")
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
        else:
            logger.info("skip_rag=True，跳过 RAG 长文生成 + LLM 直接生成")
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
        if (self.enable_explanation and not fast_mode and not skip_rag) and retrieval.paths:
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
        elif not retrieval.paths and not skip_rag:
            # KG 未匹配时生成友好提示（快速模式也保留，但 skip_rag 跳过）
            available_policies = self._get_available_policies()
            explanation = self.explanation_generator.generate_no_match(available_policies)

        # ══════════════════════════════════════════
        # Phase 1: Step 4 条件核验 + Step 5 申报方案
        # ══════════════════════════════════════════
        application_plans = []
        eligibility_results = []
        if retrieval.matched_policies:
            engine = EligibilityEngine(profile, neo4j_store=self.neo4j_store)
            detector = MissingInfoDetector()

            for policy_name in retrieval.matched_policies:
                # Step 3: KG 条件展开
                cond_texts = self.retriever.get_policy_condition_texts(policy_name)

                # Step 4: 条件执行核验
                elig_result = engine.check_policy(
                    policy_name=policy_name,
                    policy_id=policy_name,  # 暂用名称作为 ID
                    conditions=cond_texts,
                )
                eligibility_results.append(elig_result)

                # Step 5: 构建 ApplicationPlan
                app_data = self._get_policy_application_data(policy_name)
                plan = ApplicationPlan(
                    policy_name=policy_name,
                    policy_id=policy_name,
                    is_eligible=elig_result.is_eligible,
                    eligibility_result=elig_result,
                    # 结构化字段从 KG 一次性批量读取
                    required_materials=app_data.get("required_materials", []),
                    application_steps=app_data.get("application_steps", []),
                    deadline=app_data.get("deadline", ""),
                    platform_url=app_data.get("application_platform_url", ""),
                    platform_name=app_data.get("application_platform", ""),
                    source_department=app_data.get("contact_department", ""),
                    policy_doc_id=app_data.get("doc_id", ""),
                    estimated_amount=app_data.get("estimated_amount", ""),
                    effective_date=app_data.get("effective_date", ""),
                    expiry_date=app_data.get("expiry_date", ""),
                    policy_status=app_data.get("status", ""),
                )
                application_plans.append(plan)

            # 按可申报性排序：可申报在前，不可申报在后
            application_plans.sort(key=lambda p: (not p.is_eligible, p.policy_name))

            # LLM 生成 match_explanation 和 suggestions（仅对可申报政策）
            eligible_plans = [p for p in application_plans if p.is_eligible]
            if eligible_plans:
                self._generate_plan_texts(query, profile, eligible_plans)

            # Step 4.5: 缺失信息检测
            missing_info = detector.detect(eligibility_results)
        else:
            missing_info = None

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
            # ── Phase 1 新增 ──
            application_plans=application_plans,
            missing_info=missing_info,
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

    # ══════════════════════════════════════════
    # Phase 2: 申报方案辅助方法
    # ══════════════════════════════════════════

    def _get_policy_application_data(self, policy_name: str) -> dict:
        """
        从 Neo4j 一次性批量读取 Policy 的申报相关属性

        使用 FIND_POLICY_APPLICATION_DATA 替代原来逐属性查询的 _get_policy_attr()
        8次查询 → 1次查询，消除 N+1 问题
        """
        if not self.neo4j_store:
            return {}

        try:
            from src.storage.cypher_queries import FIND_POLICY_APPLICATION_DATA
            with self.neo4j_store.driver.session(database=self.neo4j_store.database) as session:
                result = session.run(FIND_POLICY_APPLICATION_DATA, policy_name=policy_name)
                record = result.single()
                if record:
                    # 过滤掉 None 值，只保留有数据的属性
                    return {key: record[key] for key in record.keys() if record[key] is not None}
        except Exception as e:
            logger.debug(f"批量读取 Policy 申报属性失败: {policy_name} - {e}")

        return {}

    def _get_policy_attr(self, policy_name: str, attr: str, default=None):
        """
        从 Neo4j Policy 节点读取单个属性（兼容旧调用方）

        优先使用 _get_policy_application_data() 批量查询，此方法保留做 fallback
        """
        if not self.neo4j_store:
            return default

        try:
            with self.neo4j_store.driver.session(database=self.neo4j_store.database) as session:
                result = session.run(
                    f"MATCH (p:Policy {{name: $name}}) RETURN p.{attr} AS val",
                    name=policy_name,
                )
                record = result.single()
                if record and record["val"] is not None:
                    return record["val"]
        except Exception as e:
            logger.debug(f"读取 Policy.{attr} 失败: {e}")

        return default

    def _generate_plan_texts(
        self,
        query: str,
        profile: EnterpriseProfile,
        plans: list[ApplicationPlan],
    ):
        """
        用 LLM 为可申报政策并行生成 match_explanation 和 suggestions

        每政策一次独立 LLM 调用，ThreadPoolExecutor 并发执行。
        N 个政策的耗时 = max(单次调用) 而非 sum(单次调用)。
        """
        if not plans:
            return

        # 构建每政策的独立 prompt
        plan_prompts = []
        for p in plans:
            checks_summary = ""
            if p.eligibility_result:
                for c in p.eligibility_result.checks:
                    icon = "✓" if c.status == "pass" else "?" if c.status == "unknown" else "✗"
                    checks_summary += f"  {icon} {c.condition_text}\n"

            app_info = ""
            if p.estimated_amount:
                app_info += f"补贴金额: {p.estimated_amount}\n"
            if p.deadline:
                app_info += f"截止日期: {p.deadline}\n"
            if p.platform_name:
                app_info += f"申报平台: {p.platform_name}\n"

            prompt = f"""企业画像:
地区: {profile.region}, 行业: {profile.industry}, 类型: {profile.company_type}
高新企业: {profile.is_high_tech}, 中小微: {profile.is_sme}

政策: {p.policy_name}
{app_info}
条件核验:
{checks_summary}
{"可申报" if p.is_eligible else "条件不符"}

请生成:
1. match_explanation: 该政策为何匹配/不匹配此企业（1句话）
2. suggestions: 申报建议（1句话）

仅输出 JSON: {{"match_explanation":"...","suggestions":"..."}}"""

            plan_prompts.append((p, prompt))

        def _gen_one(plan: ApplicationPlan, prompt: str):
            """单个政策的 LLM 调用（在 ThreadPool 中执行）"""
            try:
                raw = self.llm.chat_json(
                    system_prompt="你是一个政策申报顾问。只输出 JSON，不要解释。",
                    user_prompt=prompt,
                    temperature=0.2,
                )
                if isinstance(raw, dict):
                    plan.match_explanation = raw.get("match_explanation", "")
                    plan.suggestions = raw.get("suggestions", "")
                return
            except Exception as e:
                logger.warning(f"生成 {plan.policy_name[:30]} 文本失败: {e}")
            # fallback
            plan.match_explanation = "条件已通过核验" if plan.is_eligible else "部分条件不满足"
            plan.suggestions = "请确认政策原文要求"

        # 并行执行
        max_workers = min(len(plan_prompts), 10)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_gen_one, plan, prompt): plan.policy_name
                for plan, prompt in plan_prompts
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.warning(f"并行生成异常: {futures[future]} - {e}")


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

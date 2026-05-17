"""
路径转文本转换器

将图遍历的 ReasoningPath 列表转为虚拟段落文本
虚拟段落供 RAG Generator 作为上下文使用
"""

from loguru import logger

from src.decision.graph_retriever import RetrievalResult, ReasoningPath


class PathToTextConverter:
    """推理路径 → 虚拟段落文本"""

    def convert(self, retrieval_result: RetrievalResult) -> str:
        """
        将检索结果转为虚拟段落

        Args:
            retrieval_result: 图检索结果

        Returns:
            虚拟段落文本
        """
        if not retrieval_result.paths:
            return "未找到与该企业匹配的政策信息。"

        # 按 policy 分组
        policy_groups: dict[str, list[ReasoningPath]] = {}
        for path in retrieval_result.paths:
            if path.policy_name not in policy_groups:
                policy_groups[path.policy_name] = []
            policy_groups[path.policy_name].append(path)

        paragraphs = []

        for policy_name, paths in policy_groups.items():
            # 条件描述
            conditions_text = self._format_conditions(paths[0].conditions)

            # 措施描述
            actions_text = self._format_actions(paths)

            # 策略描述
            strategies_text = self._format_strategies(paths)

            para = (
                f"《{policy_name}》适用于{conditions_text}，"
                f"提供{actions_text}，"
                f"可帮助企业{strategies_text}。"
            )
            paragraphs.append(para)

        result = "\n\n".join(paragraphs)
        logger.debug(f"路径转文本: {len(paragraphs)} 段, {len(result)} 字符")
        return result

    @staticmethod
    def _format_conditions(conditions: list[dict]) -> str:
        """格式化条件列表"""
        parts = []
        for c in conditions:
            cat = c.get("category", "")
            val = c.get("value", "")
            if cat == "region":
                parts.append(f"{val}地区")
            elif cat == "company_type":
                parts.append(val)
            elif cat == "industry":
                parts.append(f"{val}行业")
        return "、".join(parts) if parts else "相关企业"

    @staticmethod
    def _format_actions(paths: list[ReasoningPath]) -> str:
        """格式化措施描述（优先用关系上的 source_text）"""
        action_parts = []
        seen = set()
        for p in paths:
            if p.action_type in seen:
                continue
            seen.add(p.action_type)

            # 优先用关系上的 source_text（含原文片段）
            if p.provides_source_text:
                action_parts.append(f"{p.action_type}：{p.provides_source_text}")
            elif p.action_raw:
                raw_str = "、".join(p.action_raw)
                action_parts.append(f"{p.action_type}（{raw_str}）")
            else:
                # 无 raw 无 source_text → 只显示 action_type 名
                action_parts.append(p.action_type)

        return "；".join(action_parts) if action_parts else "相关支持措施"

    @staticmethod
    def _format_strategies(paths: list[ReasoningPath]) -> str:
        """格式化策略描述"""
        all_strategies = []
        seen = set()
        for p in paths:
            for s in p.strategies:
                if s not in seen:
                    seen.add(s)
                    all_strategies.append(s)
        return "、".join(all_strategies) if all_strategies else "发展"

"""
Strategy 规则映射器

纯规则：ActionType 6 大类 → Strategy 列表
不调用 LLM，确定性映射
"""

from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from src.extraction.schema import ACTION_TO_STRATEGIES, ACTION_CATEGORIES


@dataclass
class StrategyMapping:
    """策略映射结果"""
    action_type: str             # 6 大类名称
    strategies: list[str]        # 对应策略列表


class StrategyMapper:
    """ActionType → Strategy 纯规则映射"""

    def __init__(self):
        # 验证映射完整性
        for cat in ACTION_CATEGORIES:
            if cat not in ACTION_TO_STRATEGIES:
                logger.warning(f"Action 类别 '{cat}' 缺少 Strategy 映射")

    def map_action_to_strategies(self, action_type: str) -> list[str]:
        """
        将 Action 大类映射为 Strategy 列表

        Args:
            action_type: 6 大类名称

        Returns:
            策略名称列表
        """
        strategies = ACTION_TO_STRATEGIES.get(action_type, [])
        if not strategies:
            logger.debug(f"Action '{action_type}' 无 Strategy 映射")
        return strategies

    def map_all(self, action_types: list[str]) -> list[StrategyMapping]:
        """
        批量映射

        Args:
            action_types: 去重后的 Action 大类列表

        Returns:
            StrategyMapping 列表
        """
        results = []
        seen_strategies = set()
        for action_type in action_types:
            strategies = self.map_action_to_strategies(action_type)
            # 去重：不同 Action 可能映射到相同 Strategy
            unique_strategies = [s for s in strategies if s not in seen_strategies]
            seen_strategies.update(strategies)
            if unique_strategies:
                results.append(StrategyMapping(
                    action_type=action_type,
                    strategies=unique_strategies,
                ))
        return results

"""
关系归一化器

将 LLM 输出的多样化关系名映射到标准关系名，分三层处理：
- 强归一：语义等价，直接替换不保留原名（如"鼓励"="支持" → supports）
- 弱归一：语义相近但有差异，替换关系名但双写保留原始名（如"补贴" → provides, raw_relation="补贴"）
- 不归一：语义独立，各自保留

映射表外置到 config/relation_normalization.json，与代码解耦。
"""

import json
from pathlib import Path
from datetime import date

from loguru import logger

from config.settings import settings


class RelationNormalizer:
    """关系归一化器"""

    def __init__(self, mapping_path: Path | None = None):
        """
        Args:
            mapping_path: 归一化映射表路径，默认使用 settings 中的路径
        """
        self.mapping_path = mapping_path or settings.RELATION_NORMALIZATION_FILE
        self.strong_map: dict[str, str] = {}     # raw → normalized
        self.weak_map: dict[str, str] = {}       # raw → normalized
        self.direction_tags: dict[str, str] = {}  # raw → positive/negative
        self._load_mapping()

    def _load_mapping(self):
        """加载归一化映射表"""
        if not self.mapping_path.exists():
            logger.warning(f"归一化映射表不存在: {self.mapping_path}，使用空映射")
            return

        try:
            data = json.loads(self.mapping_path.read_text(encoding="utf-8"))
            self.strong_map = data.get("strong_normalization", {})
            self.weak_map = data.get("weak_normalization", {})
            self.direction_tags = data.get("direction_tags", {})
            logger.info(
                f"归一化映射表加载: 强归一 {len(self.strong_map)} 条, "
                f"弱归一 {len(self.weak_map)} 条, "
                f"方向标签 {len(self.direction_tags)} 条"
            )
        except Exception as e:
            logger.error(f"加载归一化映射表失败: {e}")

    def _save_mapping(self):
        """保存归一化映射表（候选池回写时调用）"""
        data = {
            "strong_normalization": self.strong_map,
            "weak_normalization": self.weak_map,
            "direction_tags": self.direction_tags,
            "_meta": {
                "last_updated": date.today().isoformat(),
                "strong_count": len(self.strong_map),
                "weak_count": len(self.weak_map),
            },
        }
        self.mapping_path.parent.mkdir(parents=True, exist_ok=True)
        self.mapping_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def normalize(self, relation: str) -> tuple[str, bool, str]:
        """
        归一化关系名

        Args:
            relation: 原始关系名

        Returns:
            (归一化后的关系名, 是否发生了归一化, 归一化类型)
            归一化类型: "strong" | "weak" | ""
        """
        # 1. 强归一：直接替换，不保留原名
        if relation in self.strong_map:
            return self.strong_map[relation], True, "strong"

        # 2. 弱归一：替换关系名，但调用方应保留原始关系名到 raw_relation
        if relation in self.weak_map:
            return self.weak_map[relation], True, "weak"

        # 3. 不归一
        return relation, False, ""

    def add_mapping(self, raw_relation: str, normalized_as: str, level: str = "weak"):
        """
        添加新的归一化映射（候选池转正时自动调用）

        Args:
            raw_relation: 原始关系名
            normalized_as: 归一化目标关系名
            level: 归一化层级 "strong" 或 "weak"
        """
        if level == "strong":
            if raw_relation not in self.strong_map:
                self.strong_map[raw_relation] = normalized_as
                logger.info(f"强归一映射新增: '{raw_relation}' → '{normalized_as}'")
        else:
            if raw_relation not in self.weak_map:
                self.weak_map[raw_relation] = normalized_as
                logger.info(f"弱归一映射新增: '{raw_relation}' → '{normalized_as}'")

        self._save_mapping()

    def add_direction_tag(self, relation: str, direction: str):
        """
        添加方向标签（候选池方向校验时使用）

        Args:
            relation: 关系名
            direction: "positive" | "negative"
        """
        self.direction_tags[relation] = direction
        self._save_mapping()

    @property
    def mapping(self) -> dict[str, str]:
        """返回完整的映射表（强归一+弱归一合并），供候选池使用"""
        result = {}
        result.update(self.strong_map)
        result.update(self.weak_map)
        return result

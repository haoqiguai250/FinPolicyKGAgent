"""
候选关系池

管理未通过 Schema 校验的关系类型，支持：
- 语义聚类入池（编辑距离 + 共实体类型 + 方向校验）
- 双条件自动转正（count + unique_source_files）
- 候选三元组完整数据保存 + 关系转正后回填
- 审计日志 + 回滚机制

双文件存储：
- data/candidate_relations.json: 关系类型元数据
- data/candidate_triples.json: 候选三元组完整数据
"""

import json
from pathlib import Path
from datetime import date

from loguru import logger

from config.settings import settings
from src.extraction.schema import RELATION_CONSTRAINTS


def _levenshtein(a: str, b: str) -> int:
    """计算两个字符串的编辑距离"""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if len(b) == 0:
        return len(a)
    prev_row = range(len(b) + 1)
    for i, ca in enumerate(a):
        curr_row = [i + 1]
        for j, cb in enumerate(b):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (0 if ca == cb else 1)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


class CandidatePool:
    """候选关系池"""

    def __init__(
        self,
        normalizer=None,
        relations_path: Path | None = None,
        triples_path: Path | None = None,
    ):
        """
        Args:
            normalizer: RelationNormalizer 实例（方向校验依赖它）
            relations_path: 候选关系数据文件路径
            triples_path: 候选三元组数据文件路径
        """
        self.normalizer = normalizer
        self.relations_path = relations_path or settings.CANDIDATE_RELATIONS_FILE
        self.triples_path = triples_path or settings.CANDIDATE_TRIPLES_FILE
        self.data: dict = {"pending": [], "promoted": [], "rejected": []}
        self.pooled_triples: list[dict] = []
        self._dirty = False          # 关系元数据脏标记
        self._triple_dirty = False   # 候选三元组脏标记
        self._load()

    def _load(self):
        """加载候选池数据"""
        # 加载关系元数据
        if self.relations_path.exists():
            try:
                self.data = json.loads(self.relations_path.read_text(encoding="utf-8"))
                # 兼容旧格式
                self.data.setdefault("pending", [])
                self.data.setdefault("promoted", [])
                self.data.setdefault("rejected", [])
            except Exception as e:
                logger.warning(f"加载候选关系池失败: {e}")

        # 加载候选三元组
        if self.triples_path.exists():
            try:
                self.pooled_triples = json.loads(self.triples_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"加载候选三元组失败: {e}")

    def _save(self):
        """保存候选关系元数据"""
        self.relations_path.parent.mkdir(parents=True, exist_ok=True)
        self.relations_path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_triples(self):
        """保存候选三元组"""
        self.triples_path.parent.mkdir(parents=True, exist_ok=True)
        self.triples_path.write_text(
            json.dumps(self.pooled_triples, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_or_merge(
        self,
        raw_relation: str,
        head_type: str,
        tail_type: str,
        example: str = "",
        source_file: str = "",
    ) -> bool:
        """
        添加或合并候选关系

        语义聚类逻辑：
        1. 完全匹配 → 计数+1
        2. 编辑距离 ≤ 1 + 同头尾类型 + 同方向 → 合并（aliases）
        3. 全新关系 → 入池

        Args:
            raw_relation: 原始关系名
            head_type: 头实体类型
            tail_type: 尾实体类型
            example: 示例三元组描述
            source_file: 来源文件名

        Returns:
            是否成功入池/合并
        """
        # Step 1: 完全匹配
        for entry in self.data["pending"]:
            if (entry["raw_relation"] == raw_relation
                    and entry["head_type"] == head_type
                    and entry["tail_type"] == tail_type):
                entry["occurrence_count"] += 1
                entry["last_seen"] = date.today().isoformat()
                if example and example not in entry.get("examples", []):
                    entry.setdefault("examples", []).append(example)
                if source_file and source_file not in entry.get("unique_source_files", []):
                    entry.setdefault("unique_source_files", []).append(source_file)
                self._dirty = True
                return True

        # Step 2: 语义聚类（编辑距离 + 共实体类型 + 方向校验）
        for entry in self.data["pending"]:
            if (entry["head_type"] == head_type
                    and entry["tail_type"] == tail_type
                    and self._is_similar(raw_relation, entry["raw_relation"])
                    and self._same_direction(raw_relation, entry["raw_relation"])):
                # 合并到已有条目
                if raw_relation not in entry.get("aliases", []):
                    entry.setdefault("aliases", [])
                    if raw_relation not in entry["aliases"]:
                        entry["aliases"].append(raw_relation)
                entry["occurrence_count"] += 1
                entry["last_seen"] = date.today().isoformat()
                if source_file and source_file not in entry.get("unique_source_files", []):
                    entry.setdefault("unique_source_files", [])
                    if source_file not in entry["unique_source_files"]:
                        entry["unique_source_files"].append(source_file)
                entry.setdefault("audit_log", []).append({
                    "date": date.today().isoformat(),
                    "action": "merged",
                    "detail": f"'{raw_relation}' 合并到 '{entry['raw_relation']}' (编辑距离相似)"
                })
                self._dirty = True
                return True

        # Step 3: 全新关系
        self.data["pending"].append({
            "raw_relation": raw_relation,
            "head_type": head_type,
            "tail_type": tail_type,
            "occurrence_count": 1,
            "unique_source_files": [source_file] if source_file else [],
            "first_seen": date.today().isoformat(),
            "last_seen": date.today().isoformat(),
            "examples": [example] if example else [],
            "aliases": [],
            "audit_log": [{
                "date": date.today().isoformat(),
                "action": "add",
                "detail": f"首次出现，来源: {source_file}"
            }]
        })
        self._dirty = True
        return True

    @staticmethod
    def _is_similar(a: str, b: str) -> bool:
        """
        编辑距离相似度判定（中文优化）

        - 短词（≤2字符）：精确匹配，不允许编辑距离聚类
        - 多字词：编辑距离 ≤ 1（中文字符语义密度高，阈值 2 过于宽松）
        """
        if abs(len(a) - len(b)) > 1:
            return False
        if len(a) <= 2:
            return a == b
        return _levenshtein(a, b) <= 1

    def _same_direction(self, rel_a: str, rel_b: str) -> bool:
        """
        语义方向校验：防止字形相近但语义相反的词被误合并

        两层防护，零 LLM 调用：
        1. 归一化规则联动：映射表中归一化目标不同 → 方向不同 → 不合并
        2. 方向词表兜底：映射表外的词查 direction_tags
        """
        if self.normalizer is None:
            # 无归一化器时保守拒绝
            return False

        # 层1：归一化规则联动
        norm_a, _, _ = self.normalizer.normalize(rel_a)
        norm_b, _, _ = self.normalizer.normalize(rel_b)
        if norm_a in RELATION_CONSTRAINTS and norm_b in RELATION_CONSTRAINTS:
            if norm_a != norm_b:
                return False  # 归一化目标不同 → 方向不同
            else:
                return True   # 归一化目标相同 → 方向相同

        # 层2：方向词表兜底
        dir_tags = self.normalizer.direction_tags if self.normalizer else {}
        dir_a = dir_tags.get(rel_a, "unknown")
        dir_b = dir_tags.get(rel_b, "unknown")
        if dir_a != "unknown" and dir_b != "unknown":
            return dir_a == dir_b

        # 无法判断，保守拒绝
        return False

    def promote(
        self,
        raw_relation: str,
        normalized_as: str,
        by: str = "auto_threshold",
    ) -> bool:
        """自动转正或人工转正"""
        entry = self._find_pending(raw_relation)
        if not entry:
            return False

        count = entry["occurrence_count"]
        self.data["promoted"].append({
            "raw_relation": raw_relation,
            "normalized_as": normalized_as,
            "promoted_at": date.today().isoformat(),
            "by": by,
            "occurrence_at_promotion": count,
            "audit_log": [{
                "date": date.today().isoformat(),
                "action": f"{'auto_' if by == 'auto_threshold' else ''}promoted",
                "detail": f"occurrence_count={count} 达到阈值，转正为 {normalized_as}"
            }]
        })
        self.data["pending"].remove(entry)

        # 联动：回写归一化映射表
        if normalized_as and self.normalizer:
            self.normalizer.add_mapping(raw_relation, normalized_as)

        # 联动：回填候选三元组
        self._backfill_pooled_triples(raw_relation, normalized_as)

        self._dirty = True
        return True

    def add_pooled_triple(self, t_data: dict, reason: str):
        """将 POOL 级别的三元组完整数据保存到 candidate_triples.json"""
        entry = {
            "subject": t_data.get("subject", {}),
            "relation": t_data.get("relation", ""),
            "object": t_data.get("object", {}),
            "confidence": t_data.get("confidence", 0.5),
            "source_text": t_data.get("source_text", ""),
            "source_chunk_id": t_data.get("source_chunk_id", ""),
            "source_file": t_data.get("source_file", ""),
            "pooled_at": date.today().isoformat(),
            "pool_reason": reason,
        }
        self.pooled_triples.append(entry)
        self._triple_dirty = True

    def flush(self):
        """批量写盘：仅在脏标记为 True 时保存"""
        if self._dirty:
            self._save()
            self._dirty = False
        if self._triple_dirty:
            self._save_triples()
            self._triple_dirty = False

    def _backfill_pooled_triples(self, raw_relation: str, normalized_as: str) -> list:
        """关系转正后，回填候选三元组到 Stage4（Neo4j + JSON）"""
        backfilled = []
        remaining = []
        for pt in self.pooled_triples:
            if pt["relation"] == raw_relation:
                pt["relation"] = normalized_as
                pt["confidence"] = 0.7
                pt["source"] = "pool_backfill"
                backfilled.append(pt)
            else:
                remaining.append(pt)
        self.pooled_triples = remaining
        if backfilled:
            self._triple_dirty = True

        if backfilled:
            logger.info(f"回填候选三元组: '{raw_relation}' → '{normalized_as}', {len(backfilled)} 条")
            # 将回填的三元组写入 JSON 备份文件（供后续手动导入 Neo4j）
            backfill_path = settings.TRIPLETS_DIR / f"backfill_{date.today().isoformat()}.json"
            backfill_path.parent.mkdir(parents=True, exist_ok=True)
            backfill_path.write_text(
                json.dumps(backfilled, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(f"回填三元组已保存: {backfill_path}")

        return backfilled

    def rollback(self, raw_relation: str, reason: str = "") -> bool:
        """回滚已转正的关系"""
        entry = self._find_promoted(raw_relation)
        if not entry:
            return False

        self.data["rejected"].append({
            "raw_relation": raw_relation,
            "rejected_at": date.today().isoformat(),
            "by": "manual_rollback",
            "reason": reason or "人工回滚"
        })
        self.data["promoted"].remove(entry)

        # 从归一化映射表移除
        if self.normalizer:
            changed = False
            if raw_relation in self.normalizer.strong_map:
                del self.normalizer.strong_map[raw_relation]
                changed = True
            if raw_relation in self.normalizer.weak_map:
                del self.normalizer.weak_map[raw_relation]
                changed = True
            if changed:
                self.normalizer._save_mapping()

        self._dirty = True
        logger.info(f"候选关系回滚: '{raw_relation}', 原因: {reason}")
        return True

    def check_auto_promote(self):
        """检查所有 pending 条目，达到阈值的自动转正（含语义方向校验）"""
        for entry in list(self.data["pending"]):
            count = entry["occurrence_count"]
            unique_sources = len(entry.get("unique_source_files", []))

            threshold = settings.AUTO_PROMOTE_THRESHOLD
            min_sources = settings.MIN_PROMOTE_SOURCES

            if count < threshold or unique_sources < min_sources:
                continue

            # 语义方向校验：负面关系不自动转正为 provides
            raw = entry["raw_relation"]
            if self.normalizer:
                dir_tag = self.normalizer.direction_tags.get(raw, "unknown")
                if dir_tag == "negative":
                    logger.info(f"跳过自动转正（负面关系）: '{raw}'")
                    continue

            normalized = self._guess_normalized_relation(entry["raw_relation"])
            self.promote(entry["raw_relation"], normalized, by="auto_threshold")
            logger.info(
                f"自动转正: '{entry['raw_relation']}' → '{normalized}' "
                f"(count={count}, sources={unique_sources})"
            )

    def _guess_normalized_relation(self, raw_relation: str) -> str:
        """猜测候选关系应归一化到哪个标准关系"""
        # 先查归一化映射表
        if self.normalizer:
            norm, changed, _ = self.normalizer.normalize(raw_relation)
            if changed:
                return norm

        # 兜底：根据头尾类型猜测
        # Policy → ActionType 的未知关系，大概率是 provides
        entry = self._find_pending(raw_relation)
        if entry:
            if entry["head_type"] == "Policy" and entry["tail_type"] == "ActionType":
                return "provides"
            if entry["head_type"] == "Policy" and entry["tail_type"] == "Condition":
                return "has_eligibility"

        return raw_relation  # 实在猜不出，保持原名

    def count(self, relation: str, head_type: str, tail_type: str) -> int:
        """查询候选池中某关系的出现次数（含 aliases）"""
        for entry in self.data["pending"]:
            if (entry["head_type"] == head_type
                    and entry["tail_type"] == tail_type
                    and (entry["raw_relation"] == relation
                         or relation in entry.get("aliases", []))):
                return entry["occurrence_count"]
        return 0

    def is_promoted(self, relation: str) -> bool:
        """检查关系是否已被转正"""
        return any(e["raw_relation"] == relation for e in self.data["promoted"])

    def _find_pending(self, raw_relation: str) -> dict | None:
        """在 pending 列表中查找条目"""
        for entry in self.data["pending"]:
            if entry["raw_relation"] == raw_relation:
                return entry
        return None

    def _find_promoted(self, raw_relation: str) -> dict | None:
        """在 promoted 列表中查找条目"""
        for entry in self.data["promoted"]:
            if entry["raw_relation"] == raw_relation:
                return entry
        return None

    def export_for_review(self) -> str:
        """导出候选池供人工审核"""
        output_path = settings.EXPORTS_DIR / f"candidate_review_{date.today().isoformat()}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {"relations": self.data, "triples": self.pooled_triples},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        logger.info(f"候选池导出: {output_path}")
        return str(output_path)

    @property
    def pending_count(self) -> int:
        return len(self.data.get("pending", []))

    @property
    def promoted_count(self) -> int:
        return len(self.data.get("promoted", []))

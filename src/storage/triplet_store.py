"""
Stage 4: 三元组存储模块（JSON 版）
后续迁移到 Neo4j 时替换此模块

功能：
- 保存三元组为 JSON 文件
- 合并去重
- 统计查询
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict

from loguru import logger

from src.extraction.schema import Entity, Triple
from config.settings import settings


@dataclass
class TripletStore:
    """三元组存储（JSON 格式）"""

    source_file: str = ""
    policy_id: str = ""
    extract_time: str = ""
    entities: list[dict] = field(default_factory=list)
    triples: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def add_entities(self, entities: list[Entity]) -> int:
        """添加实体（去重）"""
        existing_keys = {(e["name"], e["type"]) for e in self.entities}
        added = 0
        for e in entities:
            key = (e.name, e.entity_type)
            if key not in existing_keys:
                self.entities.append({
                    "name": e.name,
                    "type": e.entity_type,
                    "attributes": e.attributes,
                    "source_chunk_id": e.source_chunk_id,
                })
                existing_keys.add(key)
                added += 1
        return added

    def add_triples(self, triples: list[Triple]) -> int:
        """添加三元组（去重）"""
        existing_keys = {
            (t["subject"]["name"], t["relation"], t["object"]["name"])
            for t in self.triples
        }
        added = 0
        for t in triples:
            key = (t.subject.name, t.relation, t.object_.name)
            if key not in existing_keys:
                self.triples.append(t.to_dict())
                existing_keys.add(key)
                added += 1
        return added

    def compute_stats(self) -> dict:
        """计算统计信息"""
        entity_types = {}
        for e in self.entities:
            etype = e["type"]
            entity_types[etype] = entity_types.get(etype, 0) + 1

        relation_types = {}
        for t in self.triples:
            rel = t["relation"]
            relation_types[rel] = relation_types.get(rel, 0) + 1

        self.stats = {
            "total_entities": len(self.entities),
            "total_triples": len(self.triples),
            "entity_type_distribution": entity_types,
            "relation_type_distribution": relation_types,
        }
        return self.stats

    def save(self, output_path: Optional[Path] = None) -> Path:
        """保存为 JSON 文件"""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = settings.TRIPLETS_DIR / f"{self.source_file}_{timestamp}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.compute_stats()
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

        logger.info(f"三元组已保存: {output_path}")
        logger.info(f"统计: {self.stats.get('total_entities', 0)} 实体, "
                     f"{self.stats.get('total_triples', 0)} 三元组")
        return output_path

    @classmethod
    def load(cls, path: Path) -> "TripletStore":
        """从 JSON 文件加载"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        store = cls(
            source_file=data.get("source_file", ""),
            policy_id=data.get("policy_id", ""),
            extract_time=data.get("extract_time", ""),
            entities=data.get("entities", []),
            triples=data.get("triples", []),
            stats=data.get("stats", {}),
        )
        return store

    def merge(self, other: "TripletStore") -> dict:
        """合并另一个 store（去重），返回合并统计"""
        ent_added = self.add_entities(
            [Entity(name=e["name"], entity_type=e["type"],
                    attributes=e.get("attributes", {}),
                    source_chunk_id=e.get("source_chunk_id", ""))
             for e in other.entities]
        )
        tri_added = self.add_triples(
            [Triple(
                subject=Entity(name=t["subject"]["name"],
                               entity_type=t["subject"]["type"]),
                relation=t["relation"],
                object_=Entity(name=t["object"]["name"],
                               entity_type=t["object"]["type"]),
                confidence=t.get("confidence", 1.0),
                source_text=t.get("source_text", ""),
            ) for t in other.triples]
        )
        return {"entities_added": ent_added, "triples_added": tri_added}

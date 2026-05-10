"""
数据格式适配器

将后端 Python 数据结构转换为前端 TypeScript 期望的 JSON 格式。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger


# ══════════════════════════════════════════
# KG 图谱数据适配
# ══════════════════════════════════════════

def adapt_graph_data(raw: dict) -> dict:
    """
    将后端 _export_to_dict() 的格式转换为前端 GraphData 格式

    后端: {entities: [{name, type, attributes, source_chunk_id}], triples: [{subject, relation, object, ...}], stats: {...}}
    前端: {nodes: [{id, name, type, properties}], edges: [{id, source, target, relation, source_chunk_id, properties}]}
    """
    nodes = []
    edges = []

    # 实体 → 节点
    for entity in raw.get("entities", []):
        node = {
            "id": entity["name"],  # 用 name 作为唯一 ID（Neo4j MERGE 保证同名同类型唯一）
            "name": entity["name"],
            "type": entity["type"],
            "properties": entity.get("attributes", {}),
        }
        # source_chunk_id 放进 properties
        if entity.get("source_chunk_id"):
            node["properties"]["source_chunk_id"] = entity["source_chunk_id"]
        nodes.append(node)

    # 三元组 → 边
    for triple in raw.get("triples", []):
        subj_name = triple["subject"]["name"] if isinstance(triple["subject"], dict) else str(triple["subject"])
        obj_name = triple["object"]["name"] if isinstance(triple["object"], dict) else str(triple["object"])
        relation = triple["relation"]

        edge = {
            "id": f"{subj_name}_{relation}_{obj_name}",
            "source": subj_name,
            "target": obj_name,
            "relation": relation,
            "source_chunk_id": triple.get("source_chunk_id", ""),
            "properties": {
                "confidence": triple.get("confidence", 1.0),
                "source_text": triple.get("source_text", ""),
            },
        }
        edges.append(edge)

    return {"nodes": nodes, "edges": edges}


# ══════════════════════════════════════════
# 评估报告适配
# ══════════════════════════════════════════

def adapt_evaluation_data(reports_dir: Path) -> dict:
    """
    从 logs/pipeline/*.json 读取评估数据，转换为前端 EvaluationData 格式

    前端期望:
    {
        summary: { total_docs, avg_l1, avg_l2, avg_l3, avg_l4 },
        reports: [{ id, doc_name, timestamp, l1, l2, l3, l4 }]
    }
    """
    reports = []

    # 查找所有 run_*.json
    if not reports_dir.exists():
        logger.warning(f"报告目录不存在: {reports_dir}")
        return _empty_evaluation_data()

    json_files = sorted(reports_dir.glob("run_*.json"))

    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"读取报告失败 {json_file.name}: {e}")
            continue

        eval_data = data.get("stage5_evaluate")
        if not eval_data:
            continue

        # 跳过空评估（0 实体 0 三元组通常是未完成的运行）
        if eval_data.get("total_entities", 0) == 0 and eval_data.get("total_triples", 0) == 0:
            continue

        report = _adapt_single_report(eval_data, data.get("run_meta", {}))
        if report:
            reports.append(report)

    if not reports:
        return _empty_evaluation_data()

    # 计算汇总
    summary = {
        "total_docs": len(reports),
        "avg_l1": round(sum(r["l1"]["overall_rate"] for r in reports) / len(reports), 1),
        "avg_l2": round(sum(r["l2"]["ecr"] * 100 + r["l2"]["tcr"] * 100 + r["l2"]["rcr"] * 100 for r in reports) / len(reports) / 3, 1),
        "avg_l3": round(sum(r["l3"]["diversity_score"] for r in reports) / len(reports), 1),
        "avg_l4": round(sum(r["l4"]["overall_score"] for r in reports) / len(reports), 1),
    }

    return {"summary": summary, "reports": reports}


def _adapt_single_report(eval_data: dict, run_meta: dict) -> Optional[dict]:
    """将后端 EvaluationReport 的 asdict 输出转换为前端格式"""

    cr = eval_data.get("check_rules", {})
    le = eval_data.get("local_efficiency", {})
    sd = eval_data.get("semantic_diversity", {})
    lj = eval_data.get("llm_judge", {})

    # L1: 规则合规
    total = cr.get("total_triples", 0)
    compliant = cr.get("fully_compliant_count", 0)
    rate = cr.get("compliance_rate", 0)
    overall_rate = round(rate * 100, 1) if rate <= 1 else round(rate, 1)

    l1_rules = [
        {
            "rule": "R1: 实体名非空",
            "description": "所有三元组的主体和客体实体名称不能为空",
            "pass": cr.get("vague_reference_violations", 0) == 0,
            "rate": round((1 - cr.get("vague_reference_violations", 0) / max(total, 1)) * 100, 1),
            "details": f"模糊引用违规: {cr.get('vague_reference_violations', 0)} 条",
        },
        {
            "rule": "R2: 实体名长度合规",
            "description": "实体名长度应 ≤ 50 字符",
            "pass": cr.get("entity_length_violations", 0) == 0,
            "rate": round((1 - cr.get("entity_length_violations", 0) / max(total, 1)) * 100, 1),
            "details": f"长度违规: {cr.get('entity_length_violations', 0)} 条",
        },
        {
            "rule": "R3: 实体类型合规",
            "description": "实体类型必须属于预定义 Schema",
            "pass": cr.get("entity_type_violations", 0) == 0,
            "rate": round((1 - cr.get("entity_type_violations", 0) / max(total, 1)) * 100, 1),
            "details": f"类型违规: {cr.get('entity_type_violations', 0)} 条",
        },
        {
            "rule": "R4: 关系类型合规",
            "description": "关系类型必须属于预定义 Schema",
            "pass": cr.get("relation_type_violations", 0) == 0,
            "rate": round((1 - cr.get("relation_type_violations", 0) / max(total, 1)) * 100, 1),
            "details": f"关系违规: {cr.get('relation_type_violations', 0)} 条",
        },
    ]

    # L2: 抽取效率
    l2 = {
        "ecr": round(le.get("ecr", 0), 4),
        "tcr": round(le.get("tcr", 0), 4),
        "rcr": round(le.get("rcr", 0), 4),
        "doc_breakdown": [],  # 单文档模式无 breakdown
    }

    # L3: 语义多样性
    # 将 entity_type_distribution 转为比例
    etd = eval_data.get("entity_type_distribution", {})
    total_entities = eval_data.get("total_entities", 1) or 1
    type_dist = {k: round(v / total_entities, 2) for k, v in etd.items()} if isinstance(etd, dict) else {}

    shannon = sd.get("shannon_entropy_entity", 0)
    renyi = sd.get("renyi_entropy_entity", 0)
    # 多样性评分 = (Shannon / max_possible_entropy) * 100，简化为 shannon * 20 上限截断
    diversity_score = min(round(shannon * 20, 0), 100)

    l3 = {
        "shannon_entropy": round(shannon, 2),
        "renyi_entropy": round(renyi, 2),
        "type_distribution": type_dist,
        "diversity_score": int(diversity_score),
    }

    # L4: LLM 裁判
    precision = round(lj.get("precision", 0) * 100)
    faithfulness = round(lj.get("faithfulness", 0) * 100)
    comprehensiveness = round(lj.get("comprehensiveness", 0) * 100)
    relevance = round(lj.get("relevance", 0) * 100)
    overall = round(lj.get("overall_score", 0) * 100)

    l4 = {
        "dimensions": [
            {"name": "精确性", "score": precision, "color": "#3b82f6"},
            {"name": "忠实度", "score": faithfulness, "color": "#10b981"},
            {"name": "完整性", "score": comprehensiveness, "color": "#f59e0b"},
            {"name": "相关性", "score": relevance, "color": "#8b5cf6"},
        ],
        "overall_score": overall,
        "llm_judge_comments": lj.get("judge_reasoning", ""),
        "doc_scores": [],
    }

    # 生成报告 ID
    source_file = eval_data.get("source_file", "unknown")
    run_time = run_meta.get("run_time", "")
    report_id = f"rpt-{run_time.replace('-', '').replace(':', '').replace(' ', '-').replace('.', '')[:15]}" if run_time else f"rpt-{source_file[:10]}"

    return {
        "id": report_id,
        "doc_name": source_file.replace(".pdf", ""),
        "timestamp": run_time or datetime.now().isoformat(),
        "l1": {
            "overall_rate": overall_rate,
            "rules": l1_rules,
        },
        "l2": l2,
        "l3": l3,
        "l4": l4,
    }


def _empty_evaluation_data() -> dict:
    """空的评估数据（无报告时返回）"""
    return {
        "summary": {
            "total_docs": 0,
            "avg_l1": 0,
            "avg_l2": 0,
            "avg_l3": 0,
            "avg_l4": 0,
        },
        "reports": [],
    }

"""
Pipeline 运行记录器
每次运行 pipeline 生成一个 Markdown 文件 + 一个 JSON 文件，记录所有阶段的中间产物

输出路径:
  - Markdown: logs/pipeline/{source_file}_{timestamp}.md
  - JSON:    logs/pipeline/run_{timestamp}.json
"""

import json
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

from loguru import logger

from config.settings import settings


class PipelineRunLogger:
    """Pipeline 运行记录器 — 追加写入 Markdown 文件"""

    def __init__(self, source_file: str):
        """
        Args:
            source_file: 源文件名（如 xxx.pdf）
        """
        self.source_file = source_file
        self.run_time = datetime.now()

        timestamp = self.run_time.strftime("%Y%m%d_%H%M%S")
        stem = Path(source_file).stem
        self.log_path = settings.PIPELINE_LOGS_DIR / f"{stem}_{timestamp}.md"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件头
        self._write_header()

    def _append(self, text: str) -> None:
        """追加内容到 Markdown 文件"""
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(text)

    def _write_header(self) -> None:
        """写入文件头"""
        time_str = self.run_time.strftime("%Y-%m-%d %H:%M:%S")
        content = f"""# FinPolicyKG Pipeline 运行记录

- **源文件**: {self.source_file}
- **运行时间**: {time_str}

---

"""
        self._append(content)
        logger.info(f"运行记录文件已创建: {self.log_path}")

    # ── Stage 1: 文档解析 ──

    def log_stage1_input(self, file_path: Path) -> None:
        """记录 Stage 1 输入文件信息"""
        size_kb = file_path.stat().st_size / 1024
        content = f"""## Stage 1: 文档解析

### 输入文件
- **文件名**: {file_path.name}
- **文件大小**: {size_kb:.1f} KB
- **文件类型**: {file_path.suffix.lstrip('.')}

"""
        self._append(content)

    def log_stage1_output(self, parsed_doc) -> None:
        """记录 Stage 1 解析后全文"""
        sections_info = "\n".join(
            f"  - {s.get('heading', '无标题')} (层级 {s.get('level', 0)}, {len(s.get('content', ''))} 字符)"
            for s in parsed_doc.sections
        )
        content = f"""### 解析结果
- **标题**: {parsed_doc.title}
- **章节数**: {len(parsed_doc.sections)}
- **全文长度**: {len(parsed_doc.full_text)} 字符

#### 章节概览
{sections_info}

### 解析后全文（Markdown）

```
{parsed_doc.full_text}
```

---

"""
        self._append(content)

    # ── Stage 2: 章节感知分割 ──

    def log_stage2_input(self, parsed_doc) -> None:
        """记录 Stage 2 分割前信息"""
        content = f"""## Stage 2: 章节感知分割

### 分割前
- **章节数**: {len(parsed_doc.sections)}
- **全文长度**: {len(parsed_doc.full_text)} 字符

"""
        self._append(content)

    def log_stage2_output(self, chunked_doc) -> None:
        """记录 Stage 2 每个 chunk 详情"""
        chunks_detail = ""
        total_tokens = 0
        for chunk in chunked_doc.chunks:
            chunks_detail += f"""#### {chunk.chunk_id} — {chunk.heading}
- **token 估算**: {chunk.token_count}
- **字符数**: {len(chunk.text)}
- **章节序号**: {chunk.chapter_idx}

```
{chunk.text}
```

"""
            total_tokens += chunk.token_count

        content = f"""### 分割后
- **Chunk 数**: {len(chunked_doc.chunks)}
- **总 token 估算**: {total_tokens}
- **政策文号**: {chunked_doc.policy_id or '未识别'}

### Chunk 详情

{chunks_detail}---

"""
        self._append(content)

    # ── Stage 3: 反思式智能体抽取 ──

    def log_stage3_summary(self, all_reflection_results: list) -> None:
        """记录 Stage 3 反思迭代摘要 + 最终三元组 + 迭代日志"""
        total_iterations = sum(r.iterations for r in all_reflection_results)
        all_converged = all(r.converged for r in all_reflection_results) if all_reflection_results else False

        # 汇总所有三元组
        all_triples = []
        all_entities = []
        for r in all_reflection_results:
            all_triples.extend(r.triples)
            all_entities.extend(r.entities)

        # 三元组表格
        triple_table = "| # | 主语 | 关系 | 宾语 |\n|---|------|------|------|\n"
        for i, t in enumerate(all_triples, 1):
            triple_table += f"| {i} | {t.subject.name} | {t.relation} | {t.object_.name} |\n"

        # 实体列表
        entity_list = ""
        entity_types = {}
        for e in all_entities:
            entity_types[e.entity_type] = entity_types.get(e.entity_type, 0) + 1

        entity_dist = "\n".join(f"  - {k}: {v}" for k, v in sorted(entity_types.items(), key=lambda x: -x[1]))

        # 迭代日志
        iteration_log = ""
        for idx, r in enumerate(all_reflection_results):
            iteration_log += f"#### Chunk {idx + 1}\n"
            iteration_log += f"- **迭代轮次**: {r.iterations}\n"
            iteration_log += f"- **是否收敛**: {'是' if r.converged else '否'}\n"
            iteration_log += f"- **实体数**: {len(r.entities)}\n"
            iteration_log += f"- **三元组数**: {len(r.triples)}\n\n"

            if r.iteration_log:
                iteration_log += "| 轮次 | 阶段 | 结果 | 详情 |\n|------|------|------|------|\n"
                for entry in r.iteration_log:
                    action = entry.get("action", "")
                    if action == "critique":
                        passed = entry.get("passed", False)
                        issue_count = entry.get("issue_count", 0)
                        detail = f"{'通过' if passed else f'发现 {issue_count} 个问题'}"
                        iteration_log += f"| {entry.get('round', '')} | 反馈 | {'PASS' if passed else 'ISSUES'} | {detail} |\n"
                    elif action == "revise":
                        change_rate = entry.get("change_rate", 0)
                        iteration_log += f"| {entry.get('round', '')} | 修正 | 变更率 {change_rate:.1%} | {entry.get('old_count', 0)} → {entry.get('new_count', 0)} 三元组 |\n"
                iteration_log += "\n"

        content = f"""## Stage 3: 反思式智能体抽取

### 迭代摘要
- **总迭代轮次**: {total_iterations}
- **是否全部收敛**: {'是' if all_converged else '否'}
- **实体数**: {len(all_entities)}
- **三元组数**: {len(all_triples)}

### 实体类型分布
{entity_dist}

### 最终三元组（共 {len(all_triples)} 条）

{triple_table}

### 迭代日志

{iteration_log}---

"""
        self._append(content)

    # ── Stage 4: 三元组存储 ──

    def log_stage4_output(self, store) -> None:
        """记录 Stage 4 存储结果"""
        # 实体类型分布
        entity_types = {}
        for e in store.entities:
            entity_types[e["type"]] = entity_types.get(e["type"], 0) + 1
        entity_dist = "\n".join(f"  - {k}: {v}" for k, v in sorted(entity_types.items(), key=lambda x: -x[1]))

        # 关系类型分布
        relation_types = {}
        for t in store.triples:
            relation_types[t["relation"]] = relation_types.get(t["relation"], 0) + 1
        relation_dist = "\n".join(f"  - {k}: {v}" for k, v in sorted(relation_types.items(), key=lambda x: -x[1]))

        content = f"""## Stage 4: 三元组存储

### 存储统计
- **实体数**: {len(store.entities)}
- **三元组数**: {len(store.triples)}
- **源文件**: {store.source_file}
- **政策文号**: {store.policy_id or '未识别'}
- **提取时间**: {store.extract_time or '未记录'}

### 实体类型分布
{entity_dist}

### 关系类型分布
{relation_dist}

---

"""
        self._append(content)

    # ── Stage 5: 评估 ──

    def log_stage5_output(self, report) -> None:
        """记录 Stage 5 完整评估报告"""
        report_text = report.to_text()

        content = f"""## Stage 5: 多维度评估

```
{report_text}
```

---
"""
        self._append(content)

    # ── Enhancement: 补图 ──

    def log_enhancement_output(self, store, ent_added: int, tri_added: int,
                               extraction_results: list = None) -> None:
        """记录补图结果（Action/Eligibility/Strategy）"""

        # Action 大类统计
        action_types = {}
        for e in store.entities:
            if e.get("type") == "ActionType":
                cat = e.get("name", "")
                raws = e.get("attributes", {}).get("raw", [])
                action_types[cat] = raws

        action_detail = ""
        for cat, raws in action_types.items():
            raw_list = "\n".join(f"    - {r}" for r in raws)
            action_detail += f"  - **{cat}**: {len(raws)} 条原始措施\n{raw_list}\n"

        # Eligibility 统计
        eligibility_list = ""
        for e in store.entities:
            if e.get("type") == "Condition":
                eligibility_list += f"  - {e.get('name', '')}\n"

        # Strategy 统计
        strategy_list = ""
        for t in store.triples:
            if t.get("relation") == "leads_to":
                strategy_list += f"  - ({t['subject']['name']}) -[leads_to]-> ({t['object']['name']})\n"

        content = f"""## 补图：Action + Eligibility + Strategy

### 补图统计
- **新增实体**: {ent_added}
- **新增三元组**: {tri_added}

### Action 大类
{action_detail if action_detail else "  无"}

### Eligibility（适用条件）
{eligibility_list if eligibility_list else "  无"}

### Strategy（策略推导）
{strategy_list if strategy_list else "  无"}

---
"""
        self._append(content)

    # ── Reasoning: 推理查询 ──

    def log_reasoning_output(self, query: str, result: dict) -> None:
        """记录推理查询的输入和结果"""

        matched_conditions = result.get("matched_conditions", [])
        matched_policies = result.get("matched_policies", [])
        actions = result.get("actions", [])
        strategies = result.get("strategies", [])
        explanation = result.get("explanation", "")

        cond_list = "\n".join(f"  - {c}" for c in matched_conditions) if matched_conditions else "  无"
        policy_list = "\n".join(f"  - {p}" for p in matched_policies) if matched_policies else "  无"
        action_list = "\n".join(f"  - {a}" for a in actions) if actions else "  无"
        strat_list = "\n".join(f"  - {s}" for s in strategies) if strategies else "  无"

        content = f"""## 推理查询

### 查询输入
- **企业描述**: {query}

### 匹配条件
{cond_list}

### 匹配政策
{policy_list}

### 可用措施
{action_list}

### 推荐策略
{strat_list}

### 解释
{explanation if explanation else "无"}

---

*运行记录生成完毕*
"""
        self._append(content)
        logger.info(f"运行记录已保存: {self.log_path}")


# ══════════════════════════════════════════
# JSON 运行记录器 — 每次运行一个 JSON，记录每个 Stage 的输出
# ══════════════════════════════════════════

class JsonRunLogger:
    """
    Pipeline 运行记录器（JSON 格式）

    每次运行生成一个 JSON 文件，按 stage key 记录各阶段输出。
    线性管线中输入就是上一阶段的输出，因此只记输出不记输入。

    输出路径: logs/pipeline/run_{timestamp}.json
    结构示例:
    {
        "run_meta": { "source_file": "...", "run_time": "...", "duration_sec": 0 },
        "stage1_parse": { ... },
        "stage2_chunk": { ... },
        "stage3_extract": { ... },
        "stage4_store": { ... },
        "stage5_evaluate": { ... },
        "enhancement": { ... }
    }
    """

    def __init__(self, source_file: str):
        self.source_file = source_file
        self.run_time = datetime.now()
        self._data: dict = {
            "run_meta": {
                "source_file": source_file,
                "run_time": self.run_time.strftime("%Y-%m-%d %H:%M:%S"),
                "duration_sec": 0,
            }
        }

        # 使用时间戳(含毫秒) + 源文件名哈希，确保并行时文件名唯一
        # 同一文档不同时刻运行 → 时间戳不同
        # 不同文档同一时刻运行 → 文件哈希不同
        import hashlib
        file_hash = hashlib.md5(source_file.encode()).hexdigest()[:6]
        timestamp = self.run_time.strftime("%Y%m%d_%H%M%S_") + f"{self.run_time.microsecond // 1000:03d}"
        self.log_path = settings.PIPELINE_LOGS_DIR / f"run_{timestamp}_{file_hash}.json"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _serialize_entity(self, e) -> dict:
        """序列化 Entity 对象"""
        return {
            "name": e.name,
            "entity_type": e.entity_type,
            "attributes": e.attributes,
            "source_chunk_id": e.source_chunk_id,
        }

    def _serialize_triple(self, t) -> dict:
        """序列化 Triple 对象"""
        return t.to_dict()

    def _serialize_chunk(self, c) -> dict:
        """序列化 Chunk 对象"""
        return {
            "chunk_id": c.chunk_id,
            "heading": c.heading,
            "chapter_idx": c.chapter_idx,
            "section_idx": c.section_idx,
            "token_count": c.token_count,
            "text": c.text,
        }

    # ── Stage 1: 文档解析 ──

    def log_stage1(self, parsed_doc) -> None:
        """记录 Stage 1 解析输出"""
        self._data["stage1_parse"] = {
            "title": parsed_doc.title,
            "source_file": parsed_doc.source_file,
            "doc_type": parsed_doc.doc_type,
            "full_text": parsed_doc.full_text,
            "sections": parsed_doc.sections,
            "metadata": parsed_doc.metadata,
        }

    # ── Stage 2: 章节感知分割 ──

    def log_stage2(self, chunked_doc) -> None:
        """记录 Stage 2 分块输出"""
        self._data["stage2_chunk"] = {
            "source_file": chunked_doc.source_file,
            "policy_id": chunked_doc.policy_id,
            "publish_date": chunked_doc.publish_date,
            "source_url": chunked_doc.source_url,
            "chunks": [self._serialize_chunk(c) for c in chunked_doc.chunks],
        }

    # ── Stage 3: 反思式抽取 ──

    def log_stage3(self, all_reflection_results: list) -> None:
        """记录 Stage 3 抽取输出（实体 + 三元组 + 迭代日志）"""
        all_entities = []
        all_triples = []
        reflection_details = []

        for idx, r in enumerate(all_reflection_results):
            all_entities.extend(r.entities)
            all_triples.extend(r.triples)
            reflection_details.append({
                "chunk_index": idx,
                "iterations": r.iterations,
                "converged": r.converged,
                "entity_count": len(r.entities),
                "triple_count": len(r.triples),
                "iteration_log": r.iteration_log,
            })

        self._data["stage3_extract"] = {
            "entities": [self._serialize_entity(e) for e in all_entities],
            "triples": [self._serialize_triple(t) for t in all_triples],
            "total_iterations": sum(r.iterations for r in all_reflection_results),
            "all_converged": all(r.converged for r in all_reflection_results) if all_reflection_results else False,
            "reflection_details": reflection_details,
        }

    # ── Stage 4: 三元组存储 ──

    def log_stage4(self, store) -> None:
        """记录 Stage 4 去重合并后的存储输出"""
        self._data["stage4_store"] = {
            "source_file": store.source_file,
            "policy_id": store.policy_id,
            "extract_time": store.extract_time,
            "entities": store.entities,
            "triples": store.triples,
            "stats": store.stats,
        }

    # ── Stage 5: 评估 ──

    def log_stage5(self, report) -> None:
        """记录 Stage 5 评估报告"""
        cr = report.check_rules
        le = report.local_efficiency
        sd = report.semantic_diversity
        lj = report.llm_judge

        self._data["stage5_evaluate"] = {
            "source_file": report.source_file,
            "total_entities": report.total_entities,
            "total_triples": report.total_triples,
            "avg_confidence": report.avg_confidence,
            "reflection_iterations": report.reflection_iterations,
            "reflection_converged": report.reflection_converged,
            "check_rules": {
                "total_triples": cr.total_triples,
                "fully_compliant_count": cr.fully_compliant_count,
                "compliance_rate": cr.compliance_rate,
                "vague_reference_violations": cr.vague_reference_violations,
                "entity_length_violations": cr.entity_length_violations,
                "entity_type_violations": cr.entity_type_violations,
                "relation_type_violations": cr.relation_type_violations,
                "violation_details": cr.violation_details,
            },
            "local_efficiency": {
                "avg_triples_per_chunk": le.avg_triples_per_chunk,
                "ecr": le.ecr,
                "tcr": le.tcr,
                "rcr": le.rcr,
                "tcr_normalized": le.tcr_normalized,
                "rcr_normalized": le.rcr_normalized,
            },
            "semantic_diversity": {
                "shannon_entropy_entity": sd.shannon_entropy_entity,
                "shannon_entropy_relation": sd.shannon_entropy_relation,
                "schema_normalized_entropy_entity": sd.schema_normalized_entropy_entity,
                "schema_normalized_entropy_relation": sd.schema_normalized_entropy_relation,
                "renyi_entropy_entity": sd.renyi_entropy_entity,
                "renyi_entropy_relation": sd.renyi_entropy_relation,
            },
            "llm_judge": {
                "precision": lj.precision,
                "faithfulness": lj.faithfulness,
                "comprehensiveness": lj.comprehensiveness,
                "relevance": lj.relevance,
                "overall_score": lj.overall_score,
                "judge_reasoning": lj.judge_reasoning,
            },
            "entity_type_distribution": report.entity_type_distribution,
            "relation_type_distribution": report.relation_type_distribution,
        }

    # ── Enhancement: 补图 Sidecar ──

    def log_enhancement(self, enhancement_data: dict) -> None:
        """记录补图 Sidecar 输出（Action/Eligibility/Strategy）"""
        self._data["enhancement"] = enhancement_data

    # ── 保存 ──

    def save(self) -> Path:
        """将所有阶段输出写入单个 JSON 文件"""
        # 记录总耗时
        elapsed = (datetime.now() - self.run_time).total_seconds()
        self._data["run_meta"]["duration_sec"] = round(elapsed, 2)

        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

        logger.info(f"JSON 运行记录已保存: {self.log_path}")
        return self.log_path

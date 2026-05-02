"""
Pipeline 运行记录器
每次运行 pipeline 生成一个 Markdown 文件，记录所有阶段的中间产物

输出路径: data/run_logs/{source_file}_{timestamp}.md
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
        self.log_path = settings.RUN_LOGS_DIR / f"{stem}_{timestamp}.md"
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

*运行记录生成完毕*
"""
        self._append(content)
        logger.info(f"运行记录已保存: {self.log_path}")

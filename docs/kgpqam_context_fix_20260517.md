# KG-PQAM 评分修正 + Context 生成修复

> 日期：2026-05-17
> 修改范围：KG-PQAM 评分权重/匹配逻辑 + Cypher 查询 + Context 生成

---

## 一、KG-PQAM 评分修正

### 1.1 权重调整

| 指标 | 旧权重 | 新权重 | 原因 |
|------|--------|--------|------|
| Δ字符重叠率 | 5% | 10% | 客观指标可信度提升 |
| Δ实体保留率 | 10% | 30% | 修复匹配逻辑后权重上调 |
| Δ关键词覆盖率 | 10% | 30% | 修复匹配逻辑后权重上调 |
| LLM 语义分 | **75%** | **30%** | LLM 裁判对信息密度变化不敏感，降低依赖 |

文件：`src/decision/perturbator.py` 第 69-76 行

### 1.2 实体/关键词匹配逻辑修复

**旧逻辑**（有 Bug）：
```python
pert_hit = sum(1 for e in entity_names if e in perturbed_answer)
# "降低融资成本" in "已为您梳理降低融资成本等政策" → True → 误判为"实体还在"
```

**新逻辑**（正则匹配）：
```python
def _entity_has_detail(entity_name, text):
    pattern = re.escape(entity_name) + r"[：:，,。\s]?[^。]*?\d+"
    return bool(re.search(pattern, text))
# "降低融资成本" in "已为您梳理降低融资成本等政策" → 无数字 → False → 正确判为"实体丢失"
```

新增方法：
- `_entity_has_detail()`: 实体名 + 同句内至少一个数字才算命中
- `_keyword_has_detail()`: 关键词 + 同句内数值（最高X万/Y%等）才算命中

文件：`src/decision/perturbator.py` 第 573-612 行

### 1.3 LLM 裁判 Prompt 修正

**旧 prompt**：关注"语义是否完整"
**新 prompt**：关注"具体数值/金额/百分比是否丢失"

评分标准更新为：
- 1.0：删除后具体数值/金额/百分比大幅减少或消失（关键节点）
- 0.7-0.9：删除后明显丢失了重要数值信息（重要节点）
- 0.3-0.6：删除后部分数值信息丢失但不影响整体（中等节点）
- 0.0-0.2：删除后数值信息基本没变（冗余节点）

文件：`src/decision/perturbator.py` 第 114-126 行

### 1.4 采样配置修正

`.env` 中 `MAX_PERTURBATION_NODES` 从 `10` 改为 `0`，全量扰动不采样。

---

## 二、Context 生成修复

### 2.1 问题根因

`PathToTextConverter._format_actions()` 只用了 `action_raw` 属性。但 Neo4j 中 ActionType 节点的 `raw` 属性大多为空（102 个 ActionType 中仅 6 个有 raw）。导致 context 大量重复模板：

```
《资助技术改造项目》适用于相关企业，提供财政类（财政资金支持），可帮助企业增加投入、降低成本。
```

### 2.2 修复方案

利用 Neo4j 关系上已有的 `source_text` 属性（存有原文片段）。

**3 处修改**：

| 文件 | 改动 |
|------|------|
| `src/storage/cypher_queries.py` | `FIND_POLICY_ACTIONS` 新增 `r.source_text AS provides_source_text` |
| `src/decision/graph_retriever.py` | `_neo4j_get_policy_actions` 返回 4 元组，`ReasoningPath` 传入 `provides_source_text`，`SubPathTriple` 传入 `source_text` |
| `src/decision/path_to_text.py` | `_format_actions()` 优先级改为：`provides_source_text` > `action_raw` > `action_type` |

### 2.3 效果对比

```
改前：50万元资助（50万元资助）              ← 重复冗余
改后：50万元资助：给予最高500万元资助        ← 有原文

改前：奖励（奖励）                          ← 重复冗余
改后：奖励                                    ← 干干净净

改前：资助（资助）                           ← 重复冗余
改后：资助                                    ← 干干净净
```

### 2.4 已知局限

- `provides_source_text` 大部分仍是模板文本（如"政策提供风险类措施"），真正的原文片段仅部分存在
- `has_eligibility` 和 `leads_to` 关系的 `source_text` 暂未拼入 context
- 最根本的修复需要重新抽取 Pipeline 以生成更丰富的 ActionType `raw` 属性

---

## 三、涉及文件清单

| 文件 | 修改类型 |
|------|---------|
| `src/decision/perturbator.py` | 重写（权重、正则匹配、LLM prompt） |
| `src/decision/explanation_generator.py` | 权重回退值 |
| `src/decision/path_to_text.py` | _format_actions 逻辑重写 |
| `src/decision/graph_retriever.py` | 返回 4 元组 |
| `src/storage/cypher_queries.py` | 查询字段增加 |
| `.env` | MAX_PERTURBATION_NODES=0 |

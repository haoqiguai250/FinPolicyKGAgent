# Pipeline 性能优化记录

> 日期：2026-05-09
> 目标：将单 PDF 处理时间从 12-23 min 降至 ~5 min 以内

---

## 一、优化概述

本次优化围绕 **两个瓶颈** 展开，共涉及 `src/storage/neo4j_store.py` 和 `src/api/main.py` 两个文件：

| 优化项 | 瓶颈 | 方案 | 影响 |
|--------|------|------|------|
| **Neo4j 并行 MERGE** | Stage 4 Neo4j 写入逐条 MERGE，~290 次网络往返 | ThreadPoolExecutor 并行 MERGE，64 并发 | ~2min → ~10s |
| **三级 Pipeline 并行** | Stage 4/5/补图串行等待 | 三条线程同时跑 Neo4j ∥ 评估 ∥ 补图 | ~60s/PDF |

**预估总收益：9 PDF 批次从 12-23 min 降至 5-8 min**

---

## 二、优化一：Neo4j 并行 MERGE 写入

### 背景

`Neo4jStore.add_entities()` 和 `Neo4jStore.add_triples()` 原来是串行逐条 MERGE：
```python
# 旧方案（串行）
for e in entities:
    with self.driver.session(...) as session:
        session.run(query, ...)
```

一个 PDF 平均 ~290 个实体/三元组，每个都要独立网络往返到 Neo4j 容器，串行耗时 ~2min。

### 方案

**不改 MERGE 语义（保证与已有数据不冲突），只并行化（ThreadPoolExecutor）**。

#### 核心设计

1. **每条 entity/triple 在独立线程中执行 MERGE**
2. **每个线程创建独立 Neo4j session** — `neo4j` Python driver 支持并发 session
3. **MERGE 幂等 + 唯一约束**保证并行安全，不需要事务锁
4. **必须写实体在前、关系在后**（MERGE 关系需要节点已存在）

#### 关键代码（neo4j_store.py）

```python
def add_entities(self, entities: list[Entity]) -> int:
    def _merge_one(e: Entity) -> bool:
        label = _get_label(e.entity_type)
        props = dict(e.attributes)
        props["name"] = e.name
        props["entity_type"] = e.entity_type
        if e.source_chunk_id:
            props["source_chunk_id"] = e.source_chunk_id
        query = MERGE_NODE_TEMPLATE.format(label=label)
        with self.driver.session(database=self.database) as session:
            result = session.run(query, name=e.name, props=props)
            summary = result.consume()
            return summary.counters.nodes_created > 0

    added = 0
    max_workers = min(settings.CHUNK_PARALLEL_WORKERS, len(entities))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_merge_one, e): e for e in entities}
        for fut in as_completed(futures):
            try:
                if fut.result():
                    added += 1
            except Exception as e:
                entity = futures[fut]
                logger.warning(f"Neo4j MERGE entity 失败: {entity.name} - {e}")
    return added
```

`add_triples()` 采用完全相同的并行模式。

### 变更文件

- **`src/storage/neo4j_store.py`** — `add_entities()` + `add_triples()` 改为并行 MERGE

---

## 三、优化二：三级 Pipeline 并行

### 背景

原来 Stage 4 → Stage 5 → 补图是串行的（5阶段 Pipeline），但实际上这三阶段**数据依赖不冲突**：

| 阶段 | 需要什么 | 产生什么 |
|------|----------|----------|
| Stage 4 Neo4j 写入 | `all_entities` + `all_triples` | Neo4j 中的初始图 |
| Stage 5 评估 | 内存中的 `TripletStore` + `source_text` | 评估报告 |
| 补图抽取 | `chunked.json` + LLM | 增强的 Action/Condition/Strategy |

三者互相不依赖，可以并行。

### 方案

**三条线程同时跑**，用 `ThreadPoolExecutor(max_workers=3)` 并行执行：

```
                ┌── 线程A: Neo4j 双写 ──→ neo4j_store
                │
Stage 1-3 ──→   ├── 线程B: L1-L4 评估 ──→ report
                │
                └── 线程C: 补图抽取+写 Neo4j ──→ enhanced_store
                                                    │
                                         合并回原始 store + 保存 JSON
```

#### 线程安全设计

关键问题：`TripletStore` 不是线程安全的（`add_entities()` 直接修改内部列表）。
- **线程B（评估）**：只读内存中的 `TripletStore`，`evaluate()` 是纯读操作 → 安全
- **线程C（补图）**：传递 `store=None`，补图线程**独立创建**自己的 `TripletStore`，不碰原始 store `→` 安全
- 所有线程完成后，将补图结果合并回原始 store → writer 线程独占

#### 补图 Neo4j 独立写入

补图线程C内部也处理自己的 Neo4j 写入（Action/Condition/Strategy 节点），与线程A写入不同的实体类型，MERGE 幂等保证无冲突。

#### 关键代码（main.py）

```python
with ThreadPoolExecutor(max_workers=3) as executor:
    fut_neo4j = executor.submit(_write_neo4j)
    fut_eval = executor.submit(_run_evaluation)
    fut_enhance = executor.submit(_run_enhance)

    neo4j_store = fut_neo4j.result()
    report = fut_eval.result()
    enhanced_store = fut_enhance.result()

# 补图结果合并回原始 store
for e_data in enhanced_store.entities:
    entity = Entity(name=e_data["name"], entity_type=e_data["type"], ...)
    store.add_entities([entity])
for t_data in enhanced_store.triples:
    triple = Triple(subject=..., relation=..., object_=..., ...)
    store.add_triples([triple])
store.save()
```

### 变更文件

- **`src/api/main.py`** — `run_pipeline()` 函数中 Stage 4/5/补图三级并行架构

---

## 四、性能预估

| 场景 | 优化前 | 优化后 | 加速比 |
|------|--------|--------|--------|
| 单 PDF（~70 chunks, ~290 三元组） | 12-23 min | ~5 min | 2.4-4.6x |
| 9 PDF 批次（3 文档并行） | ~50-70 min | ~5-8 min | 6.3-14x |

**主要瓶颈转移**：原来瓶颈在 Neo4j 串行写入，现在瓶颈预计在 LLM 调用（Stage 3 抽取 + 补图抽取）。

---

## 五、相关配置项

`config/settings.py` 中：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `CHUNK_PARALLEL_WORKERS` | 64 | Neo4j 并行 MERGE 最大线程数 |
| `PARALLEL_WORKERS` | 3 | 文档级并行数（`--input-dir` 模式） |

---

## 六、后续优化方向

- [ ] LLM 调用本身可并行化（当前 chunk 间已并行，但每个 chunk 串行做 3 轮反思）
- [ ] 减少反射轮数（当前固定 3 轮，部分文档 1-2 轮即可收敛）
- [ ] 缓存相同 chunk 的 LLM 结果（跨文档重复政策条款）
- [ ] 评估 L4 LLM Judge 可降采样（当前全量评估，耗时占比较大）

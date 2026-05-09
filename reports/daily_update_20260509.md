# FinPolicyKGAgent 每日更新记录 — 2026-05-09

> 本文档记录 2026-05-09 当天完成的所有功能开发、Bug 修复和方案确认。

---

## 一、KG-PQAM 量化评估模型（完成）

### 核心设计

**KG-PQAM**（基于知识图谱扰动的政策适配性量化评估模型）完成节点级扰动 + LLM 裁判修复。

### 扰动机制

- **扰动粒度**：节点级（删整个节点 → 过滤所有包含该节点的路径 → 重新生成）
- **重要性公式**：
  ```
  importance = 0.05×Δ字符重叠 + 0.10×Δ实体保留 + 0.10×Δ关键词覆盖 + 0.75×LLM语义分
  ```
- **3 个客观指标**：
  - Δ字符重叠率（Jaccard）
  - Δ实体保留率（KG 实体命中差）
  - Δ关键词覆盖率（关键词命中差）
- **1 个主观指标**：LLM 语义分（裁判一次性对比所有扰动答案，提供显式 key 映射）
- **Fallback**：LLM 失败时前三个指标权重均分（各 33.3%）

### 数据结构

- `PerturbationNode`（name + type，key = name__type）
- `NodePerturbation`（node + importance + reason + metric_scores）

### 改动文件

| 文件 | 改动内容 |
|------|---------|
| `perturbator.py` | 核心扰动逻辑，_score_and_quantify() 评分主入口 |
| `advisor.py` | 适配节点归属 |
| `explanation_generator.py` | 节点级展示 |
| `README.md` | 更新说明 |

### LLM 裁判修复

- **问题**：prompt 未提供显式 key 映射，LLM 返回 key 格式不匹配导致默认 0.5
- **修复**：prompt 提供显式 key 映射（`key: name__type`），`_llm_judge()` 仅返回 bool

---

## 二、全链路可追溯修复（完成）

### 问题根因

`Triple` 对象内存中有 `source_chunk_id`，但 `to_dict()` 没序列化到 JSON → 写文件就丢了。

### 4 个文件改动

| 文件 | 改动内容 |
|------|---------|
| `schema.py:Triple.to_dict()` | 加 `"source_chunk_id": self.source_chunk_id` |
| `triplet_store.py:merge()` | 重建 Triple 时传入 `source_chunk_id` |
| `cypher_queries.py` | FIND_POLICY_ACTIONS / FIND_ACTION_STRATEGIES 返回关系的 `source_chunk_id` |
| `graph_retriever.py` | 双后端 sub_paths 补全 provides/leads_to 的 `source_chunk_id` |

### leads_to（Strategy）处理

规则生成，统一标记 `"rule"`，与 enhancer 一致。

---

## 三、前端开发方案确认（完成）

### 技术栈（已确认）

- **框架**：Vue 3 + TypeScript + Vite
- **UI**：Element Plus
- **图谱**：D3.js v7（力导向图）+ ECharts（统计图表）
- **状态**：Pinia / 路由：Vue Router 4 / 请求：Axios
- **不使用 uni-app**（KG 可视化在小程序受限严重）

### 4 个核心页面

1. 📊 **仪表盘（Dashboard）** — KG 统计 + 政策列表
2. 🔍 **决策查询（Advisor）** — 表单输入 + 历史侧栏 + 双路对比 + 推理路径 + 扰动分析 + 追溯
3. 🕸️ **知识图谱浏览器（KG Explorer）** — D3 力导向图 + 筛选 + 路径高亮 + 展开收缩
4. 📈 **评估报告（Evaluation）** — L1-L4 四层展示

### Boss 确认的交互决策

- 查询交互：表单式输入 + 左侧历史记录侧栏（可重复点击，localStorage 持久化）
- KG 可视化：尽量可交互（力导向 + 筛选 + 路径高亮 + 节点展开收缩 + 详情面板）
- 数据来源：**先用 Mock，后对接 FastAPI API**
- 部署：先本地 `npm run dev` 看效果
- 登录权限：暂不需要

### API 接口规划（6 个核心）

| 接口 | 方法 | 用途 |
|------|------|------|
| `/api/advise` | POST | 决策查询 |
| `/api/trace/chunk` | POST | 全链路追溯（按 chunk） |
| `/api/trace/entity` | POST | 全链路追溯（按实体） |
| `/api/kg/stats` | GET | KG 统计信息 |
| `/api/kg/graph` | GET | KG 图谱数据 |
| `/api/evaluate` | POST | 评估 |

### 前端项目位置

- `finagent/FinPolicyKGFrontend/` — 独立于后端
- 后端在 `finagent/FinPolicyKGAgent/`，前后端分开管理

### 开发节奏

P0: 脚手架 → P1: 决策查询页 → P2: 图谱可视化 → P3: 仪表盘 → P4: 评估 → P5: 打磨

---

## 四、并行抽取改造（完成）

### main.py（之前已完成）

三层并行架构：文档级 / Chunk 级 / 扰动级。

### run_e2e_test.py（本次修复）

之前遗漏串行，现已改为 `ThreadPoolExecutor`（MAX_EXTRACT_WORKERS=4）。

- 并行仅在 chunk 间，chunk 内反思循环仍串行
- 结果按原始顺序排序后写入 store

---

## 五、FastAPI 后端服务（完成）

### 服务入口

```bash
python -m src.api.main --serve  # 默认 0.0.0.0:8000
```

### 应用结构

- `src/api/server.py`：`create_app()` 工厂 + lifespan 管理 Neo4j/Advisor 单例
- `src/api/routes/`：4 个路由文件（advise / kg / trace / evaluate）
- `src/api/adapters.py`：graph_data 适配 + evaluation_data 从 run_logs 读取

### 6 个 API 路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查（status, neo4j, advisor） |
| `/api/advise` | POST | 决策查询 |
| `/api/kg/stats` | GET | KG 统计 |
| `/api/kg/graph` | GET | KG 图谱数据 |
| `/api/trace/chunk` | POST | 追溯（chunk 维度） |
| `/api/trace/entity` | POST | 追溯（实体维度） |
| `/api/evaluate` | POST | 评估 |

### 前端对接

- `.env` 文件 `VITE_USE_MOCK=false/true`，重启 Vite 生效
- Vite 代理：`/api` → `http://127.0.0.1:8000`

---

## 六、查询性能优化（完成）

### 优化前 vs 优化后

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 单次查询时间 | ~264s | ~65-70s |
| 扰动节点数 | 118（全量） | 10（采样） |
| Step4/5 | 串行 | 并行 |

### 三项改动

1. **`config/settings.py`**：新增 `MAX_PERTURBATION_NODES=10`，扰动节点按 Policy > Condition > ActionType > Strategy 优先级采样
2. **`advisor.py`**：Step4（RAG生成）+ Step5（LLM直接生成）改为 `ThreadPoolExecutor` 并行（省 ~27s）
3. **`perturbator.py`**：`analyze()` 在 `_collect_nodes()` 后加采样截断逻辑

### 前端 loading 进度

- Advisor.vue 新增 4 步进度提示（意图识别 → 图检索 → 生成 → 扰动）
- 时间估算模拟

### 统一颜色映射

- `utils/color.ts` 扩展 `nodeTypeColors`（14 种）+ `relationTypeColors`（13 种）+ `getRelColor()`
- Dashboard / Evaluation 不再硬编码

---

## 七、run_logs 评估分数丢失修复（完成）

### 问题现象

批量运行 9 个 PDF 文档，只有 2 个文档的 L1-L4 评估分数保存到了 `data/run_logs/`，其余 7 个全部丢失。

### 根因分析

1. **文件名碰撞**：`JsonRunLogger` 文件名只有秒级时间戳，`165458` 和 `165459` 两个时间点启动了 9 个并行任务，导致只有 2 个唯一文件名，后写的覆盖了先写的
2. **异常时未保存**：`json_log.save()` 只在正常流程末尾调用，异常时数据全部丢失
3. **batch_report 无评估分数**：`main.py` 的 `summary` dict 没有 `evaluation` 字段

### 修复方案（3 个文件）

#### `src/core/run_logger.py` — 文件名唯一性

```python
# 修复前
timestamp = self.run_time.strftime("%Y%m%d_%H%M%S")
self.log_path = settings.RUN_LOGS_DIR / f"run_{timestamp}.json"

# 修复后
import hashlib
file_hash = hashlib.md5(source_file.encode()).hexdigest()[:6]
timestamp = self.run_time.strftime("%Y%m%d_%H%M%S_") + f"{self.run_time.microsecond // 1000:03d}"
self.log_path = settings.RUN_LOGS_DIR / f"run_{timestamp}_{file_hash}.json"
```

- 毫秒时间戳 + 源文件 MD5 哈希，确保并行任务文件名 100% 唯一

#### `src/api/main.py` — try/finally 确保保存 + evaluation 字段

```python
report = None
try:
    # ... Stage 1-5 + enhancement ...
    report = evaluator.evaluate(...)
finally:
    json_log.save()  # 无论是否异常，必写文件

# evaluation 字段加入 summary
eval_summary = {}
if report:
    eval_summary = {
        "L1_compliance_rate": getattr(report.check_rules, "compliance_rate", None),
        "L2_ecr": getattr(report.local_efficiency, "ecr", None),
        "L3_entity_entropy": getattr(report.semantic_diversity, "shannon_entropy_entity", None),
        "L3_relation_entropy": getattr(report.semantic_diversity, "shannon_entropy_relation", None),
        "L4_overall_score": getattr(report.llm_judge, "overall_score", None),
    }
summary = {
    # ... existing fields ...
    "evaluation": eval_summary,
}
```

---

## 八、方法命名讨论（进行中）

### 候选方案

| 方案名 | 含义 |
|--------|------|
| KG-PET | Knowledge Graph Policy Evaluation & Tracing |
| DPKG-RAG | Dual-Path KG-RAG |
| PEARL | Policy Entity And Relation Linkage |
| TRACER | Traceable RAG for Policy |

### 核心特征（待 Boss 定夺）

- Method B（子图 → 虚拟段落）
- Method C（节点扰动可解释）
- 双路径生成
- 全链路追溯
- 松散交集匹配

---

## 九、待开发功能

- [ ] 政策雷达推送（定期推送新政策给企业）
- [ ] 可执行方案生成（申报步骤 + 材料清单 + 执行路径）
- [ ] 更多政策 PDF 端到端测试决策支持链路
- [ ] 方法命名最终定夺
- [ ] 重跑 9 PDF 批量验证 run_logs 修复效果

---

*文档生成时间：2026-05-09 22:06*

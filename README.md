# FinPolicyKGAgent

金融政策 PDF → 知识图谱 → 企业个性化政策建议，一站式自动完成。

系统分为两段：**5 阶段抽取管线**把政策文档变成结构化知识图谱，**3 阶段决策支持链路**让企业自然语言提问，获得可解释的政策匹配建议。

---

## 一、系统架构

```
                         ┌─────────────────────────────────────────────┐
                         │            5 阶段抽取管线                     │
                         │                                             │
  金融政策 PDF ──────→ Docling解析 ──→ 章节分块 ──→ 反思式抽取 ──→ 存储 ──→ 评估
                      (Stage 1)    (Stage 2)   (Stage 3)    (S4)   (S5)
                                                      │
                                                      │ 知识图谱 (KG)
                                                      ▼
                         ┌─────────────────────────────────────────────┐
                         │            3 阶段决策支持                     │
                         │                                             │
                         │  Phase 1 补图 ──→ Phase 2 查询 ──→ Phase 3 解释│
                         │  (Action/Condition/Strategy)  (KG-RAG)  (图扰动)│
                         │                    │                │       │
                         │                    ▼                ▼       │
                         │              个性化建议        可解释性分析   │
                         └─────────────────────────────────────────────┘
```

---

## 二、技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| 文档解析 | Docling 2.91 | 开源，支持 PDF/DOCX/HTML |
| LLM | DeepSeek-V4-Flash | Chat Completions API，支持 reasoning_effort |
| 知识存储 | Neo4j 5 Community（Docker）+ JSON 备份 | 双写，MERGE 去重，Cypher 查询 |
| 后端 | FastAPI | 待完善 |
| Python | 3.13+ | |

---

## 三、项目目录

```
FinPolicyKGAgent/
├── config/settings.py                         # 全局配置
├── src/
│   ├── core/
│   │   ├── logger.py                          # 日志
│   │   └── run_logger.py                      # 运行记录器（Markdown + JSON）
│   ├── ingestion/
│   │   ├── parser.py                          # Stage 1: Docling 文档解析
│   │   └── chunker.py                         # Stage 2: 章节感知分块
│   ├── extraction/
│   │   ├── schema.py                          # KG Schema（22实体 + 16关系）
│   │   ├── llm_client.py                      # DeepSeek 客户端
│   │   ├── extractor.py                       # Schema 引导抽取
│   │   └── reflector.py                       # Stage 3: 反思式智能体
│   ├── storage/
│   │   ├── triplet_store.py                   # Stage 4: 三元组存储（JSON 版，保留为备份）
│   │   ├── neo4j_store.py                     # Stage 4: 三元组存储（Neo4j 版，双写）
│   │   └── cypher_queries.py                  # Cypher 查询模板（约束/写入/路径查询/扰动/导出）
│   ├── evaluation/
│   │   └── evaluator.py                       # Stage 5: 四层评估
│   ├── enhancement/
│   │   ├── action_eligibility_extractor.py    # Phase 1: Action+Eligibility 抽取
│   │   ├── strategy_mapper.py                 # Phase 1: Strategy 规则映射
│   │   └── enhancer.py                        # Phase 1: 补图编排
│   ├── decision/
│   │   ├── intent_recognizer.py               # Phase 2: 意图识别
│   │   ├── graph_retriever.py                 # Phase 2: 图遍历检索
│   │   ├── path_to_text.py                    # Phase 2: 路径转文本
│   │   ├── rag_generator.py                   # Phase 2: RAG 生成
│   │   ├── perturbator.py                     # Phase 3: 图扰动
│   │   ├── explanation_generator.py           # Phase 3: 解释生成
│   │   └── advisor.py                         # Phase 2-3: 决策支持总入口
│   └── api/main.py                            # Pipeline CLI（支持并行批量处理）
├── data/
│   ├── raw/                                   # 原始政策文档
│   ├── processed/                             # 解析中间文件（*_parsed.json / *_chunked.json）
│   ├── triplets/                              # 三元组 JSON（Stage 4 输出 + 补图）
│   ├── run_logs/                              # 运行记录（.md + .json）
│   ├── output/                                # 批量汇总报告（batch_report_*.json）
│   └── reports/                               # 推理结果（advisor_result.json）
├── logs/
│   ├── batch_*                                # 并行模式独立日志（每个 PDF 各一个）
│   └── finpolicykg_*.log                      # 全局运行日志（按天轮转）
├── docs/
│   ├── FinPolicyKGAgent_Flowchart_5_2.html    # 系统架构流程图（v3 并行批量+Neo4j）
│   └── run_report_2026-05-04.html             # 4 文件并行抽取 + 2 次推理运行报告
├── scripts/
│   ├── run_e2e_test.py                        # 端到端测试
│   ├── test_decision_support.py               # 决策支持测试
│   ├── test_neo4j_connection.py               # Neo4j 连通性验证
│   ├── extract_quickstart.py                  # 快速抽取脚本
│   └── debug_docling.py                       # Docling 调试脚本
├── config/
│   └── settings.py                            # 全局配置（含 PARALLEL_WORKERS）
├── docker-compose.yml                         # Neo4j 容器一键启动
└── .env / .env.example / requirements.txt / pyproject.toml
```

---

## 四、抽取管线

一条 PDF 从进来到变成知识图谱，经过 5 个阶段：

| 阶段 | 做什么 | 关键设计 |
|------|--------|---------|
| **Stage 1** Docling 解析 | PDF → 结构化文本 | 三优先级章节识别：Docling label → 中文条款编号 → 兜底 |
| **Stage 2** 章节分块 | 按逻辑边界拆成 200-1024 token 的 chunk | 先按章节→再按条款→再按句子，太短合并太长切分 |
| **Stage 3** 反思式抽取 | 每个 chunk 抽实体+三元组 | Schema 引导 + **提取→批判→修正** 循环（最多 3 轮自动收敛） |
| **Stage 4** 三元组存储 | 去重、合并、双写 Neo4j+JSON | 14 种实体 UNIQUE CONSTRAINT（`MERGE` 去重），Neo4j 失败自动降级 JSON 备份 |
| **Stage 5** 四层评估 | 评估抽取质量 | L1 规则合规 → L2 覆盖率 → L3 语义多样性 → L4 LLM 裁判 |

**Stage 3 反思循环**是核心——LLM 先抽，再自己审（完整性/准确性/一致性/政策语义 4 个维度），不过关就改，改到收敛为止。

**Stage 5 评估四层递进**：规则硬检查 → Schema 覆盖率 → 类型分布熵 → LLM 语义评分，从客观到主观逐层深入。

---

## 五、决策支持

知识图谱建好后，企业可以用自然语言提问，系统沿图推理出匹配的政策建议，并解释"为什么"。

**推理路径**：`企业画像 → Condition ← Policy → ActionType → Strategy`

### Phase 1：补图

原始 KG 只有政策实体和基础关系，补图阶段新增三类边让图可推理：

```
Policy ──provides──→ ActionType ──leads_to──→ Strategy
Policy ──has_eligibility──→ Condition
Region ──subregion_of──→ Region（层级链）
```

- **ActionType** 分 6 大类：融资类/财政类/税收类/风险类/投资类/人才类，自动标准化归类（33 关键词映射）
- **Action 原始短语**保留在 `raw` 属性中供溯源
- **Strategy** 纯规则映射（不调 LLM）：融资类→[扩大融资能力, 扩产]，税收类→[提高利润]...
- **Condition** 强制枚举标准化（company_type 9 种 / industry 14 种），确保企业画像与 Condition 节点精确匹配
- **跨文档标准化**：Condition/ActionType/Region 等关键实体统一枚举值，Policy/Institution 等尚依赖 LLM 输出一致性

### Phase 2：查询

```
"深圳中小企业制造业能享受什么政策"
        ↓ IntentRecognizer
  企业画像: {region: 深圳, company_type: 中小企业, industry: 制造业}
        ↓ GraphRetriever（Condition⊆匹配 + Region 层级扩展）
  推理路径: 企业→Condition←Policy→ActionType→Strategy
        ↓ PathToTextConverter
  虚拟段落（供 RAG 上下文）
        ↓ RAGGenerator（LLM 生成）
  个性化建议："可通过XX银行信贷产品获得低息贷款"
```

### Phase 3：解释

基于图扰动（KG-RAG 论文方案）：逐个删除推理路径上的节点，重检索重生成，对比差异，量化每个节点的重要性。

- 重要性 > 0.7 → **关键**（核心因素）
- 0.3 ~ 0.7 → **重要**（补充因素）
- ≤ 0.3 → **次要**

---

## 六、Schema

**22 种实体**：Policy(3子类) / Institution / FinancialConcept(6子类) / Event / Indicator / Person / Document / ActionType / Condition / Strategy / Region / CompanyType / Industry

**16 种关系**：issues / modifies / repeals / affects / sets / targets / references / cites_as_basis / leads_to / mentions / has_indicator / valid_during / similar_to / provides / has_eligibility / subregion_of

每个三元组经 `validate()` 校验关系类型和主宾语类型约束，不合规自动过滤。

---

## 七、快速开始

### 7.1 环境准备

```bash
cd D:\桌面\agent实验室项目\finagent\FinPolicyKGAgent
python -m venv .venv && .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # 填入 DEEPSEEK_API_KEY
```

### 7.2 Neo4j 启动

系统使用 Neo4j 图数据库存储知识图谱。Docker 一键启动：

```bash
# 启动 Neo4j 容器
docker compose up -d
```

启动后可以通过浏览器查看和查询知识图谱：

| 项目 | 信息 |
|------|------|
| 浏览器访问 | http://localhost:7474 |
| 用户名 | `neo4j` |
| 密码 | `finagent2026` |
| 驱动连接 | `bolt://localhost:7687` |

**数据持久化说明**：
- Neo4j 数据存放在 Docker volume `neo4j_data` 中
- `docker stop` 或 `docker compose down` **不会**丢失数据
- 重新 `docker compose up -d` 即可恢复
- ⚠️ `docker compose down -v` 会删除 volume 导致数据丢失
- **双重保险**：每次运行 Pipeline 同时写 JSON 备份到 `data/triplets/`
- 数据恢复：`Neo4jStore.load_from_json("backup.json")`

### 7.2.1 查看已存储的三元组

方式一：Neo4j 浏览器（可视化，推荐）

打开 http://localhost:7474 → 登录 → 执行 Cypher 查询：

```cypher
// 查看所有节点
MATCH (n) RETURN n LIMIT 50

// 查看某个 Policy 的所有关系
MATCH (p:Policy)-[r]->(n) RETURN p, r, n

// 查看推理路径
MATCH (p:Policy)-[:has_eligibility]->(c:Condition),
      (p)-[:provides]->(a:ActionType)
OPTIONAL MATCH (a)-[:leads_to]->(s:Strategy)
RETURN p.name, c.name, a.name, s.name
```

方式二：直接打开 JSON 备份文件 `data/triplets/*.json`

方式三：用查询脚本 `python scripts/query_neo4j.py`（需创建）

### 7.3 第一步：抽取 + 补图（5 阶段管线 + Enhancer）

**方式一：命令行批量处理（推荐多 PDF 场景）**

```bash
# 单文件
python -m src.api.main --input data/raw/xxx.pdf

# 批量并行（自动 4 个同时处理）
python -m src.api.main --input-dir data/raw/

# 自定义并行数
python -m src.api.main --input-dir data/raw/ --workers 2
```

批量并行时控制台只打印开始/完成状态，每个 PDF 的详细日志独立写入 `logs/batch_xxx/` 目录，互不干扰。全部跑完后自动生成汇总报告 `data/output/batch_report_xxx.json`。

**方式二：直接运行脚本**

```bash
python scripts\run_e2e_test.py "另一个政策.pdf"
```

**耗时**：Stage 1-2 几秒，Stage 3 约 3-5 分钟（调 LLM），Stage 4-5 几十秒，补图约 10 秒。总计约 4-6 分钟。

**产出文件**：

| 产出文件 | 位置 | 来自 | 说明 |
|---------|------|------|------|
| `*_parsed.json` | `data/processed/` | Stage 1 | PDF 解析出的结构化文本 + 章节目录 |
| `*_chunked.json` | `data/processed/` | Stage 2 | 按逻辑拆好的 200-1024 token 文本块 |
| `triplets_*.json` | `data/triplets/` | Stage 4 | 抽取的实体 + 三元组（JSON 备份） |
| `*_enhanced.json` | `data/triplets/` | 补图 | 补图后的完整知识图谱（Action/Condition/Strategy） |
| `*_timestamp.md` | `data/run_logs/` | 全程 | Markdown 运行日志（人类可读） |
| `run_timestamp.json` | `data/run_logs/` | 全程 | JSON 结构化运行日志（机器可读） |

Neo4j 端数据为实时写入，无需额外文件。

### 7.4 第二步：决策支持推理

抽取 + 补图完成后，用产出的 KG 做推理查询。支持两种后端：

**Neo4j 后端（推荐，跨文档去重）：**
```bash
python -m src.decision.advisor "深圳中小企业制造业能享受什么政策" --neo4j --output data/reports/advisor_result.json
```

**JSON 后端（兼容旧数据，需指定文件路径）：**
```bash
python -m src.decision.advisor "深圳中小企业制造业能享受什么政策" --store "data\triplets\你的enhanced文件.json" --output data/reports/advisor_result.json
```

**参数说明**：

| 参数 | 说明 |
|------|------|
| `"查询语句"` | 必填，自然语言查询问题，如"深圳科技型中小企业有哪些补贴政策" |
| `--neo4j` | 使用 Neo4j 后端（从已运行的 Neo4j 读取 KG，跨文档去重） |
| `--store` | 使用 JSON 后端，后面跟补图后的 KG JSON 文件路径（完整文件名，不支持通配符） |
| `--output` | 输出结果 JSON 路径（可选，建议指定确保结果落地） |

> ⚠️ `--neo4j` 和 `--store` 二选一，都不指定会报错。
> ⚠️ JSON 文件名不支持 `*` 通配符，必须写完整文件名。

**耗时**：意图识别 1 次 LLM + RAG 生成 1 次 + 图扰动约 N 次（N=推理路径节点数），总计约 10-30 秒。

**产出文件**：

| 产出文件 | 说明 |
|---------|------|
| 第 3 个参数指定的 JSON | 结构化结果：企业画像 + 政策建议 + 匹配概况 + 解释分析 |

**推理过程 LLM 调用情况**：

| 步骤 | 模块 | 调 LLM | 做什么 |
|------|------|--------|--------|
| 意图识别 | IntentRecognizer | 是 | 自然语言 → 企业画像 |
| 图遍历检索 | GraphRetriever | 否 | 纯规则/Cypher 查询（JSON 内存索引 或 Neo4j Cypher） |
| 路径转文本 | PathToTextConverter | 否 | 纯规则拼接 |
| RAG 生成 | RAGGenerator | 是 | 虚拟段落 + 问题 → 个性化建议 |
| 图扰动 | Perturbator | 是（间接） | 每个节点扰动后重新 RAG |
| 解释生成 | ExplanationGenerator | 否 | 纯规则分级 |

### 7.5 不花钱的快速验证

用 mock 数据验证决策支持逻辑（不调 LLM）：

```bash
python scripts\test_decision_support.py
```

### 7.6 其他入口

```bash
# Pipeline CLI（支持单文件/批量）
python -m src.api.main --input data/raw/xxx.pdf
python -m src.api.main --input-dir data/raw/
```

---

## 八、运行日志

每次运行 Pipeline 在 `data/run_logs/` 生成两种格式的运行记录。批量并行模式下，每个 PDF 还有独立的详细日志：

| 日志类型 | 路径 | 说明 |
|---------|------|------|
| Markdown 运行记录 | `data/run_logs/` | 人类可读，每个阶段输入输出 |
| JSON 运行记录 | `data/run_logs/` | 结构化，机器可读 |
| 独立详细日志（并行） | `logs/batch_xxx/` | 每个 PDF 各自的完整日志 |
| 汇总报告（并行） | `data/output/batch_report_xxx.json` | 批量处理结果一览 |

### Markdown — `{source_file}_{timestamp}.md`

人类可读，记录每个阶段的输入和输出。

| 方法 | 记录内容 |
|------|---------|
| `log_stage1_input()` | 输入文件信息（文件名、大小、类型） |
| `log_stage1_output()` | 解析结果（标题、章节数、全文 Markdown） |
| `log_stage2_output()` | 每个 Chunk 详情（文本、token 估算） |
| `log_stage3_summary()` | 反思迭代摘要 + 最终三元组表格 + 迭代日志 |
| `log_stage4_output()` | 存储统计（实体/关系类型分布） |
| `log_stage5_output()` | 完整评估报告 |

### JSON — `run_{timestamp}.json`

结构化，每个 Stage 只记输出（线性管线输入 = 上一阶段输出），单文件记录全流程。

```json
{
  "run_meta": { "source_file": "...", "run_time": "...", "duration_sec": 0 },
  "stage1_parse": { "title": "...", "sections": [...], "full_text": "..." },
  "stage2_chunk": { "chunks": [{"chunk_id": "chunk_001", "text": "..."}] },
  "stage3_extract": { "entities": [...], "triples": [...], "reflection_details": [...] },
  "stage4_store": { "entities": [...], "triples": [...], "stats": {...} },
  "stage5_evaluate": { "check_rules": {...}, "local_efficiency": {...}, "semantic_diversity": {...}, "llm_judge": {...} },
  "enhancement": { ... }
}
```

| 方法 | 记录内容 |
|------|---------|
| `log_stage1(parsed_doc)` | Stage 1 解析输出 |
| `log_stage2(chunked_doc)` | Stage 2 分块输出 |
| `log_stage3(all_reflection_results)` | Stage 3 抽取输出（实体+三元组+迭代日志） |
| `log_stage4(store)` | Stage 4 去重合并后存储输出 |
| `log_stage5(report)` | Stage 5 评估报告（4 层评分详情） |
| `log_enhancement(data)` | 补图 Sidecar 输出（预留） |
| `save()` | 统一写入 JSON 文件 |

---

## 九、已知问题

（2026-05-04 核实，DeepSeek-V4-Flash，4 文件批量并行，396 实体，117 三元组）

| 问题 | 优先级 | 位置 | 说明 |
|------|--------|------|------|
| ✅ 修正阶段变量名错误 | P0 | `reflector.py:272` | `new_entities` → `entities`，已修复 |
| ✅ L4 评估未传 LLM 客户端 | P2 | `main.py:91` | `Evaluator()` → `Evaluator(llm_client=get_llm_client())`，已修复 |
| ✅ llm_client 注释残留 | P2 | `llm_client.py` | Doubao → DeepSeek，已修复 |
| `references` 关系约束过严 | 🟡 P1 | `schema.py:93` | 只允许 Policy→Policy，过滤掉 15 条合法三元组（如 Policy→InterestRate 的引用关系） |
| 修正阶段 LLM 返回格式异常 | 🟡 P1 | `reflector.py:234-238` | LLM 偶发返回 list 而非 dict，批量模式下更频繁（4 文件出现 10+ 次）。已做防御适配但修正后三元组仍可能不合规 |
| 修正阶段生成未知关系类型被过滤 | 🟡 P1 | `reflector.py` | LLM 修正时发明 Schema 外关系（"鼓励"、"发布"、"包括"、"has_validity_period"、"includes"等），全部被 validate() 丢弃。批量模式 4 文件共丢弃约 50+ 条修正结果 |
| JSON 解析失败触发 LLM 重试 | 🟡 P1 | `llm_client.py:161` | LLM 返回的 JSON 含双花括号 `{{` 等格式错误，`chat_json()` 须重试 1-2 次，每次增加 ~5s 延迟。批量 37 chunks 中出现约 10 次 |
| L1 R2 实体长度规则过严 | 🟡 P1 | `evaluator.py` | ≤15 字符规则导致 71.4% 三元组违规，政策全称/条款原文天然偏长，需放宽阈值或区分实体类型 |
| ThreadPoolExecutor 并行加速瓶颈 | 🟡 P2 | `main.py` | 4 线程并行实测 29.8min（串行估 ~76min），加速比 ~2.55x 而非理论 4x。**根本原因**：① Stage 1 OCR (RapidOCR+torch) 受 GIL 限制，4 线程在 CPU 上排队加载模型，近似串行；② Stage 3 LLM 调用虽多线程并发，但 DeepSeek API 端限流，实际并发 1-2 个；③ 单个 PDF 内 chunk 仍为串行（一个跑完才跑下一个）。实际并行效果 = B 方案（两阶段拆分）的最优理论值 |
| 批量模式收敛率低 | 🟡 P2 | `reflector.py` | 4 文档 converged 全为 false，37 chunks 总计 78 轮迭代，部分 chunk 达 3 轮上限仍未收敛 |
| RapidOCR 日志混杂 | 🔵 P3 | 日志输出 | RapidOCR 的 `[INFO]` 日志（torch 模型加载）混在 loguru 输出中，控制台杂乱 |

**Bug 影响链路**：

```
P1: schema.py references 约束 Policy→Policy
 └─→ LLM 抽取的 Policy→FinancialConcept 引用关系被 validate() 过滤
      └─→ 15 条合法三元组丢失 → 抽取覆盖率下降

P1: R2 实体长度≤15字符
 └─→ 政策全称、条款原文天然>15字符
      └─→ 71.4% 三元组被判违规 → L1 合规率虚低，评估指标失真

P1: 修正阶段 LLM 生成未知关系类型
 └─→ LLM 创 Schema 外关系（鼓励/发布/包括等），validate() 全部丢弃
      └─→ 修正阶段大量结果作废 → chunk 被迫 3 轮迭代 → 收敛率下降

P2: ThreadPoolExecutor 并行加速瓶颈
 └─→ torch RapidOCR GIL 竞争 + LLM API 限流 + chunk 内串行
      ├─解析阶段: 4 线程排队加载 OCR 模型（~8s 近似串行）
      ├─抽取阶段: LLM 并发 1-2 个（API 端限流），chunk 仍串行
      └─结果: 加速比 2.55x，总耗时 = 最慢 PDF + 排队开销
```

---

## 十、后续计划

| 功能 | 状态 |
|------|------|
| FastAPI RESTful API | 🔜 待开发 |
| 实时更新机制（监控政策网站自动触发 Pipeline） | 🔜 待开发 |
| 更多政策 PDF 端到端测试 | 🔜 待开发 |
| **并行优化：ProcessPoolExecutor 替换 ThreadPoolExecutor**（绕开 GIL，预期 20-25min） | 🔜 待开发 |
| **并行优化：两阶段拆分**（串行解析 → 并行抽取，预期 15-20min） | 🔜 待开发 |
| **并行优化：Chunk 级 LLM 异步并发**（asyncio 并行调 API，预期 10-15min） | 🔜 待开发 |
| Schema 扩展（新增关系类型减少修正丢弃） | 🔜 待优化 |
| JSON 解析容错增强（减少 LLM 重试） | 🔜 待优化 |

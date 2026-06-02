# FinPolicyKGAgent — AI 政策申报 Copilot

> 金融政策 PDF → 知识图谱 → 企业申报运营，一站式自动完成。

**产品定位**：帮企业持续运营整个补贴申报流程——从发现政策、核验条件、准备材料，到提交申报、跟踪状态。不是政策推荐工具，是申报运营平台。

---

## 一、产品流程（用户视角）

```
                            ① 填写企业画像
                            /profile 页面，15 字段
                                   │
                                   ▼
                            ② 搜索政策匹配
                      /workspace 工作台，输入自然语言
                     "深圳的高新企业能申请什么补贴？"
                                   │
                                   ▼
                            ③ 查看申报机会
                    条件核验 + 补贴金额 + 截止日期
                                   │
                                   ▼
                            ④ 管理材料清单
                    逐项勾选进度 → 100% 后进入下一步
                                   │
                                   ▼
                            ⑤ 智能日历排期
                    5 维加权排序，优先处理紧急申报
                                   │
                                   ▼
                            ⑥ 状态推进
                 discovered → applying → submitted → approved
```

### 页面导航

| 页面 | 路径 | 做什么 |
|------|------|--------|
| **画像配置** | `/profile` | 填写 15 个企业字段（地区、行业、资质、规模等） |
| **申报工作台** | `/workspace` | 自然语言搜索政策 → 查看核验结果 → 管理材料 → 推进状态 |
| **智能日历** | `/calendar` | 月视图 + 推荐排期（紧急程度排序） |
| **知识图谱** | `/kg` | 探索 KG 节点和关系 |
| **评估报告** | `/evaluation` | 查看每批 PDF 的抽取质量 |
| **决策查询** | `/advisor` | 单次推理（含可解释性评估） |
| **推送记录** | `/push-records` | 定时推送历史 |

---

## 二、快速开始

### 2.1 三步跑通

```bash
# 第 1 步：启动 Neo4j
cd FinPolicyKGAgent
docker-compose up -d

# 第 2 步：抽取建图（27 个政策 PDF）
python -m src.api.main --input-dir data/raw

# 第 3 步：启动服务
python -m src.api.main --serve
# 打开 http://localhost:8000/docs 查看 API
# 打开 http://localhost:5173 查看前端页面
```

### 2.2 环境要求

| 组件 | 说明 |
|------|------|
| Python 3.13+ | 系统后端 |
| Neo4j 5 Community | Docker 一键启动，`docker-compose up -d` |
| Node.js 22+ | 前端构建 |
| `.env` 配置 | LLM API Key（DeepSeek/OpenAI/MiMo 三选一） |

### 2.3 完整 .env 配置

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

# 可选切换
# LLM_PROVIDER=openai
# LLM_PROVIDER=mimo
```

---

## 三、技术架构

```
                        ┌──────────────────────────────────────┐
                        │          ① 抽取管线（离线）             │
                        │                                      │
  PDF ─→ Docling解析 ─→ 章节分块 ─→ LLM抽取 ─→ 本体治理 ─→ 存储 │
                        │  (Stage1)  (Stage2)  (Stage3a) (Stage3b) (S4)  │
                        │                              │              │
                        │                    归一化→候选池→分级→时序    │
                        │                                      │
                        │                              ┌───────┘
                        │                              ▼   知识图谱 (Neo4j)
                        │                    补图增强 (Enhancer)
                        │                    Action/Condition/Strategy
                        ├──────────────────────────────────────┤
                        │          ② 决策链路（在线）             │
                        │                                      │
  用户输入 ─→ 意图识别 ─→ KG检索 ─→ 条件核验 ─→ 解释评估         │
              (Intent)  (Retrieve)  (Eligibility) (Explain)   │
                        │                                      │
  输出: 匹配的政策 + 核验结果 + 材料清单 + 截止日期              │
                        ├──────────────────────────────────────┤
                        │          ③ 申报运营（在线）             │
                        │                                      │
  SQLite持久层 ─→ 材料工作台 ─→ 智能日历 ─→ 状态推进            │
   (4表+状态机)   (逐项Checklist)   (5维排期)    (事件溯源)      │
                        └──────────────────────────────────────┘
```

### 3.1 抽取管线 — 从 PDF 到知识图谱

并行架构：27 个 PDF 文件级并行（32 workers），单 PDF 内 chunk 级并行（128 workers），Neo4j 写入并行。

| 阶段 | 做什么 | 关键设计 |
|------|--------|---------|
| Stage 1 | Docling 解析 PDF → 结构化文本 | 三优先级章节识别 |
| Stage 2 | 按逻辑边界分块 | 200-2560 token/chunk，章节→条款→句子 |
| Stage 3a | LLM Schema 引导抽取 | 每 chunk 抽实体+三元组，chunk 间并行调 LLM |
| Stage 3b | 本体治理（4步） | 归一化(强/弱/负向) → 候选池(语义聚类+方向校验) → 6级分级(含约束违反检测) → 时序注入(上下文感知废止检测+精确日期计算) |
| Stage 4 | 双写 Neo4j+JSON | MERGE 去重，Neo4j 失败自动降级 JSON |
| Stage 5 | 四层评估 | L1规则 → L2覆盖率 → L3多样性 → L4 LLM裁判 |

**补图增强**（抽取后）：自动补充三类关系 + MasterPolicy 聚合 + role 过滤——
```
Policy --provides--> ActionType --leads_to--> Strategy     ← 原文句子填充
Policy --has_eligibility--> Condition                      ← applicant-only 过滤
Region --subregion_of--> Region (层级链)
MasterPolicy --contains--> Policy[1..n]                    ← 文档级聚合(amount+materials)
```

### 3.2 决策链路 — 从自然语言到政策建议

```
"深圳的高新企业能申请什么补贴？"
        ↓ IntentRecognizer (LLM, temperature=0)
企业画像: {region:深圳, is_high_tech:true, ...}
        ↓ GraphRetriever (条件交集匹配 + 区域双向扩展)
候选政策列表
        ↓ EligibilityEngine (逐条件核验)
核验结果: pass/fail/unknown + 理由
        ↓ Advisor (LLM 解释+建议)
输出: 政策名 + 核验详情 + 补贴金额 + 截止日期 + 材料清单
```

**条件核验策略**：

| 策略 | 说明 |
|------|------|
| 宽松交集匹配 | 企业条件与政策条件交集不为空即匹配 |
| Region 双向扩展 | 向上(深圳→广东→中国) + 向下(深圳→坪山区) |
| 硬/软/unknown 三级 | 硬条件 FAIL→排除；软条件 FAIL→降权；unknown→提示缺字段 |
| 空条件兜底 | 政策无 Condition 时直接匹配所有查询 |

### 3.3 申报运营 — Phase 3 核心模块

整个 Phase 3 将产品从"发现政策"推进到"运营申报全程"。

**E｜申报运营持久层**：
- SQLite 单文件数据库，替代 JSON，支持多企业管理
- 4 张表：enterprises / opportunities / opportunity_events / material_checklist
- 状态机：discovered → applying → submitted → approved / rejected，禁止回退
- 事件溯源：每次状态变更记录 old→new status + note
- 对应前端：`/workspace` 状态推进 + `/profile` 画像配置

**F｜申报材料工作台**：
- 材料从文本列表升级为逐项 Checklist（preparing/ready/submitted/waived）
- 自动展开 required_materials 为独立 item，LLM 补全缺失模板
- 对应前端：`/workspace` 材料 checkbox + 进度条 + 100%提示

**G｜智能申报日历**：
- 5 维加权排期：`deadline×0.35 + eligible×0.30 + amount×0.15 + progress×0.10 + status×0.10`
- 画像补全闭环：缺字段提示 → 自动重核验
- 对应前端：`/calendar` 日历视图 + 推荐排序

**变化对比**：

| | Phase 2（之前） | Phase 3（现在） |
|------|------|------|
| 企业画像 | 单 JSON 文件，4 字段 | SQLite 多企业，15 字段 |
| 申报机会 | 瞬态，查询完就丢 | 持久化 + 状态机 + 事件日志 |
| 材料管理 | 一段文本列表 | 逐项 Checklist + 完成度追踪 |
| 截止日期 | 只扫描提醒 | 加权排期 + 日历视图 |

**字段链路修复**（2026-05-24）：修复 Neo4j → 导出 → 前端 全链路 raw_relation/source/source_chunk_id/effective_date/expiry_date 丢失问题，6 处代码修改。

---

## 四、项目目录

```
FinPolicyKGAgent/
├── config/
│   ├── settings.py                         # 全局配置
│   └── relation_normalization.json         # 本体治理关系归一化映射表
├── src/
│   ├── ingestion/
│   │   ├── parser.py                       # Stage 1: Docling 文档解析
│   │   ├── chunker.py                      # Stage 2: 章节感知分块
│   │   └── crawler/                        # 政策采集（22源/77关键词/API搜索）
│   ├── extraction/
│   │   ├── schema.py                       # KG Schema（22实体/16关系/14 Policy属性）
│   │   ├── llm_client.py                   # UniversalLLMClient 多LLM通用客户端
│   │   ├── extractor.py                    # Schema引导抽取 + 本体治理4步
│   │   └── reflector.py                    # 反思式智能体
│   ├── enhancement/
│   │   ├── enhancer.py                     # 补图编排（Action/Condition/Strategy）
│   │   ├── action_eligibility_extractor.py # Action+Eligibility 抽取
│   │   ├── strategy_mapper.py              # Strategy 规则映射
│   │   ├── normalizer.py                   # 本体治理: 关系归一化
│   │   ├── candidate_pool.py               # 本体治理: 候选池管理
│   │   ├── triple_classifier.py            # 本体治理: 三元组6级分级
│   │   └── temporal_parser.py              # 本体治理: 时序属性注入
│   ├── decision/
│   │   ├── intent_recognizer.py            # 意图识别 → 企业画像(15字段)
│   │   ├── graph_retriever.py              # KG 图检索（条件交集+区域扩展）
│   │   ├── eligibility_engine.py           # 条件核验引擎（硬/软/unknown）
│   │   ├── path_to_text.py                 # 路径→文本转换
│   │   ├── rag_generator.py                # RAG 生成
│   │   ├── advisor.py                      # 决策支持总入口
│   │   ├── perturbator.py                  # KG-PQAM 节点级扰动量化评估
│   │   └── explanation_generator.py        # 可解释性生成
│   ├── db/
│   │   └── database.py                     # SQLite 持久层（4表+状态机+事件溯源）
│   ├── scheduling/
│   │   └── scheduler.py                    # SmartScheduler 5维加权排期
│   ├── storage/
│   │   ├── neo4j_store.py                  # Neo4j 双写 + 导出
│   │   ├── triplet_store.py                # JSON 备份存储
│   │   └── cypher_queries.py               # Cypher 查询模板
│   └── api/
│       ├── main.py                         # Pipeline CLI + FastAPI 服务入口
│       ├── server.py                       # FastAPI 应用（41 路由）
│       ├── adapters.py                     # 数据格式适配（KG→前端）
│       └── routes/
│           ├── advise.py                   # /api/advise 决策查询
│           ├── kg.py                       # /api/kg 知识图谱
│           ├── trace.py                    # /api/trace 全链路追溯
│           ├── evaluate.py                 # /api/evaluate 评估报告
│           ├── push.py                     # /api/push 推送管理
│           ├── profile.py                  # /api/profile [旧]企业画像
│           ├── enterprises.py              # /api/enterprises 多企业管理(Phase 3)
│           ├── opportunities.py            # /api/opportunities 申报机会(Phase 3)
│           ├── materials.py                # /api/materials 材料Checklist(Phase 3)
│           └── calendar.py                 # /api/calendar 智能日历(Phase 3)
├── data/
│   ├── raw/                                # 原始政策 PDF（27 个）
│   ├── processed/                          # 解析中间文件
│   ├── triplets/                           # 三元组 JSON
│   └── app.db                              # SQLite 业务数据库
├── logs/                                   # Pipeline + API 运行日志
├── outputs/                                # 报告 + 推理结果 + KG 导出
├── scripts/                                # 工具脚本
├── docker-compose.yml                      # Neo4j 一键启动
└── .env                                    # LLM API 配置
```

---

## 五、API 接口

共 41 个路由，按功能分组：

| 分组 | 主要端点 | 说明 |
|------|---------|------|
| 决策查询 | `POST /api/advise`、`/api/advise/stream`、`/api/advise/opportunities` | 自然语言→政策匹配（含 SSE 流式） |
| 知识图谱 | `GET /api/kg/graph`、`/api/kg/policy/{name}`、`/api/kg/reasoning-paths` | KG 数据查询 |
| 全链路追溯 | `POST /api/trace` | 三元组→原文溯源 |
| 评估报告 | `GET /api/evaluate/reports`、`/api/evaluate/report/{id}` | 抽取质量评估 |
| 企业管理 | `POST/GET /api/enterprises`、`GET/PUT /api/enterprises/{id}/profile`、`POST /api/enterprises/{id}/profile/nlu` | 多企业注册+画像(NLU) |
| 申报机会 | `GET /api/opportunities`、`PATCH /api/opportunities/{id}/status`、`POST /api/opportunities/{id}/refresh` | 持久化+状态机 |
| 材料管理 | `GET /api/opportunities/{id}/materials`、`PATCH /api/materials/{id}`、`POST .../materials/generate` | 逐项 Checklist |
| 智能日历 | `GET /api/enterprises/{id}/schedule`、`GET /api/calendar` | 排期+日历 |
| 推送管理 | `GET/PUT /api/push/profile`、`/api/push/preferences`、`/api/push/deadlines` | 定时推送 |

启动后访问 `http://localhost:8000/docs` 查看完整 Swagger 文档。

---

## 六、数据采集（爬虫）

系统可从政府政策网站自动采集 PDF 文件，作为抽取管线的数据入口。

### 覆盖范围

| 层级 | 数量 | 来源 |
|------|------|------|
| 国家级 | 6 | 国务院/发改委/工信部/民航局/财政部/科技部 |
| 省级 | 4 | 广东省政府/省发改委/省工信厅/省科技厅 |
| 市级 | 6 | 深圳市政府/发改委/工信局/科创委/交通局/财政局 |
| 区级 | 6 | 龙华/南山/宝安/福田/龙岗/光明 |

### CLI 用法

```bash
# 全流程：爬取 + 下载 + Pipeline
python -m src.ingestion.crawler.scheduler --run

# 查看状态
python -m src.ingestion.crawler.scheduler --status

# 仅爬取 / 仅 Pipeline
python -m src.ingestion.crawler.scheduler --crawl-only
python -m src.ingestion.crawler.scheduler --pipeline-only
```

### 政策推送

每天 17:00 定时抓取新政策，用企业画像自动推理，匹配到可申报政策时推送通知。

```bash
# 手动触发
python -m src.ingestion.crawler.push_scheduler --full
```

---

## 七、多 LLM 支持

通过 `.env` 中 `LLM_PROVIDER` 切换，`UniversalLLMClient` 统一适配：

| 提供商 | `LLM_PROVIDER` | 说明 |
|--------|----------------|------|
| DeepSeek（默认） | `deepseek` | `deepseek-v4-flash`，支持 reasoning_effort |
| OpenAI | `openai` | `gpt-4o` |
| 小米 MiMo | `mimo` | `mimo-v2.5-pro`，国产，无需科学上网 |

---

## 八、已知问题与后续计划

### 已知问题

| 问题 | 等级 | 模块 | 说明 |
|------|------|------|------|
| 申报属性命中率极低 | 🔴 P0 | 抽取管线 | deadline 0.4%、materials 1%、steps 1%、amount 10%（27 PDF，MiMo注意力衰减） |
| 条件名冗长无法核验 | 🔴 P0 | eligibility_engine | Enhancer 将长句存为 Condition.name，CANONICAL_MAP 匹配失败→"无预置定义" |
| references 关系约束过严 | 🟡 P1 | schema.py | 15 条合法三元组被过滤 |
| 修正阶段 LLM 格式异常 | 🟡 P1 | reflector.py | 偶发返回 list 非 dict |
| 深圳政策库多无 PDF 附件 | 🟡 P1 | 爬虫 | 156 条仅有 HTML 正文 |

### 近期修复

| 修复 | 日期 | 说明 |
|------|------|------|
| **本体治理层四步优化** | **2026-06-02** | 归一化细化(限制→targets/废止→repeals/修订→amends)、候选池编辑距离降为1+批量写盘+负面关系不自动转正、分级器补充 constraint_violation 检查+entity_length_exceeded 校验、时序解析器上下文感知废止检测+精确日期计算+长期有效模式+chunk全文fallback |
| MasterPolicy 文档级聚合 | 2026-05-25 | `enhancer.py` 创建文档级主节点聚合 amount + materials，Advisor 一步拿到 |
| Eligibility role 过滤 | 2026-05-25 | `action_eligibility_extractor.py` 保留 LLM 输出的 role 字段，enhancer 过滤非 applicant 条件 |
| 孤点源头过滤 | 2026-05-25 | `main.py` 写 Neo4j 时只写入参与三元组的实体，避免 32+ 孤立节点 |
| 前端节点 ID 去重 | 2026-05-25 | `adapters.py` 用 `name___type` 组合键，防止同名不同类型节点覆盖 |
| 补图线程 source_file 修复 | 2026-05-25 | `main.py` 线程C补 `set_metadata()`，修复 MasterPolicy 不创建 |
| 材料清单重复插入 | 2026-05-26 | `database.py` `add_materials()` 加同名去重，防止 opportunity 刷新时材料翻倍 |

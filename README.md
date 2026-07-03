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

## 二、环境配置

### 2.1 系统依赖

| 组件 | 版本要求 | 安装说明 |
|------|---------|-----------|
| Python | 3.13+ | [python.org](https://www.python.org/downloads/) |
| Docker Desktop | 4.x+ | [docker.com](https://www.docker.com/products/docker-desktop)（Neo4j 依赖） |
| Node.js | 22+ | [nodejs.org](https://nodejs.org/)（前端依赖） |
| Git | 任意新版 | 用于拉取代码 |

### 2.2 拉取项目

```bash
git clone <repo-url> FinPolicyKGAgent
cd FinPolicyKGAgent
```

### 2.3 Python 依赖安装

推荐使用项目自带虚拟环境：

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境（Windows PowerShell）
.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

> **注意**：项目使用 `UniversalLLMClient`，无需额外安装 LLM SDK，`openai` 包已包含在 requirements.txt 中。

### 2.4 .env 配置文件

在项目根目录创建 `.env` 文件（可复制 `.env.example`）：

```env
# ── LLM 配置（三选一）─────────────────
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

# 可选：切换 OpenAI
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-xxx

# 可选：切换 MiMo（国产，无需科学上网）
# LLM_PROVIDER=mimo
# MIMO_API_KEY=xxx
# MIMO_BASE_URL=https://token-plan-cn.xiaomimo.com/v1

# ── Neo4j 配置 ────────────────────────
NEO4J_URI=bolt://localhost:7687
NEO4J_PASSWORD=finagent2026

# ── 路径配置 ────────────────────────────
MATERIALS_OUTPUT_DIR=outputs/materials
ADVISOR_RESULTS_DIR=outputs/advisor_results
```

### 2.5 前端依赖安装

```bash
cd FinPolicyKGFrontend
npm install
```

---

## 三、Neo4j 图谱管理

> **Neo4j 是本项目的关键依赖**，所有政策知识图谱数据存储在 Neo4j 中。
> 首次使用需要启动 Neo4j 并导入数据（或恢复备份）。

### 3.1 启动 Neo4j（Docker）

```bash
# 启动 Neo4j 容器
docker-compose up -d

# 验证是否启动成功
docker ps | findstr neo4j
```

启动后访问：**http://localhost:7474**（Neo4j Browser）

```
连接参数：
  URI:      bolt://localhost:7687
  用户名:   neo4j
  密码:     finagent2026
```

### 3.2 检查现有数据

```bash
# 进入 Neo4j Browser 后执行：
MATCH (n) RETURN count(n) AS node_count;
MATCH ()-->() RETURN count(*) AS edge_count;
```

预期结果（完整数据）：
- 节点数：~2753
- 关系数：~5496

### 3.3 恢复备份数据（推荐新人）

项目提供完整的 Neo4j 备份文件，新人可以直接导入，**无需重新抽取**：

```bash
# 1. 确保 Neo4j 已启动
docker-compose up -d

# 2. 运行恢复脚本
.venv\Scripts\python.exe -m src.scripts.restore_triplets ^
  --input data/backups/neo4j_backup_20260615_181917.json

# 3. 验证恢复结果
# 进入 http://localhost:7474 执行：
# MATCH (n) RETURN count(n);
# 应返回 2753
```

### 3.4 清空图谱（重新抽取前）

```bash
# 谨慎使用！会删除所有图谱数据
.venv\Scripts\python.exe -m src.scripts.clear_neo4j
```

### 3.5 备份当前图谱

```bash
# 将当前 Neo4j 数据导出为 JSON 备份
.venv\Scripts\python.exe -m src.scripts.backup_neo4j
# → 生成文件：data/backups/neo4j_backup_YYYYMMDD_HHMMSS.json
```

### 3.6 修复地域层级关系

如果图谱中缺少「子区域 → 父区域」关系（导致深圳匹配不到坪山区政策），运行：

```bash
.venv\Scripts\python.exe -m src.scripts.fix_region_hierarchy
# 自动添加 23 条 subregion_of 关系
# 例如：坪山区 → 深圳，南山区 → 深圳
```

### 3.7 向他人分享图谱数据

有三种方式，详见本节下方「九、向他人分享 Neo4j 数据」。

---

## 四、政策抽取与建图

### 4.1 全量抽取（推荐）

```bash
# 抽取所有 PDF（55 个），16 并发
.venv\Scripts\python.exe -m src.api.main ^
  --input-dir data/raw/ ^
  --workers 16

# 预计时间：约 10-15 分钟（DeepSeek v4-flash）
```

抽取完成后：
- 数据自动写入 Neo4j
- 抽取报告保存在 `outputs/extraction/*_report.txt`
- 三元组明细保存在 `outputs/extraction/*.json`

### 4.2 单文件测试

```bash
# 测试单个 PDF 的抽取效果
.venv\Scripts\python.exe -m src.extraction.extractor ^
  --input data/raw/某政策.pdf
```

### 4.3 带反思模式（评估用）

```bash
# 开启反思（LLM 自我批判+修正循环），速度较慢
.venv\Scripts\python.exe -m src.api.main ^
  --input-dir data/raw/ ^
  --reflect True ^
  --workers 8
```

> **注意**：生产环境默认使用无反思模式（速度更快，L4 得分 0.88 > 反思 0.85）

---

## 五、启动服务

### 5.1 启动后端（FastAPI）

```bash
# 终端 1：启动后端（阻塞运行，建议独立窗口）
.venv\Scripts\python.exe -m src.api.main --serve

# 启动成功后：
#   API 文档：http://localhost:8000/docs
#   健康检查：http://localhost:8000/api/health
```

⚠️ **修改后端代码后必须重启**，否则改动不生效。

### 5.2 启动前端（Vue 3）

```bash
# 终端 2：启动前端开发服务器（阻塞运行）
cd FinPolicyKGFrontend
npm run dev

# 启动成功后访问：http://localhost:5173
```

### 5.3 验证服务正常

1. 打开 http://localhost:8000/api/health → 应返回 `{"status": "ok"}`
2. 打开 http://localhost:5173 → 应显示企业画像配置页面

---

## 六、前端使用教程

### 6.1 页面导航

| 路由 | 页面 | 功能 |
|------|------|------|
| `/` | 企业画像 | 填写 15 个企业字段 |
| `/workspace` | 申报工作台 | 政策匹配 + 条件核验 + 材料管理 |
| `/kg-explorer` | KG 图谱可视化 | 探索知识图谱节点和关系 |
| `/calendar` | 智能日历 | 申报排期 + 截止日期提醒 |

### 6.2 完整使用流程

```
第 1 步：填写企业画像（/profile）
  → 手动填写 15 个字段（地区/行业/资质/规模等）
  → 或使用「NLU 解析」自动从文本提取

第 2 步：匹配政策（/workspace）
  → 输入自然语言："深圳的高新企业能申请什么补贴？"
  → 系统返回匹配政策列表（含条件核验结果）

第 3 步：查看申报机会
  → 点击政策查看详情：核验结果 / 补贴金额 / 截止日期 / 材料清单

第 4 步：管理申报材料
  → 逐项勾选材料准备进度
  → 完成后进度条达到 100%

第 5 步：智能日历排期（/calendar）
  → 查看加权排序的申报排期
  → 优先处理紧急申报

第 6 步：推进申报状态
  → discovered → applying → submitted → approved
```

### 6.3 演示模式（Investor Demo）

用于给投资人演示，**无需真实 LLM API 调用**：

**开启方式**（二选一）：
- 快捷键：`Ctrl + Shift + D`
- 隐藏按钮：鼠标移到页面右下角，出现 `●` 圆点，点击切换

**状态指示**：
- `●`（绿色）= 演示模式开启，使用 15 条预置静态数据
- `○`（灰色）= 真实 API 模式

**演示数据流**：
```
演示模式 ON
  → 匹配时使用 demoPolicies（15 条静态数据）
  → 材料/步骤/金额/条件核验全部预置
  → 文档生成调用真实 python-docx 后端接口

演示模式 OFF
  → 正常调用 POST /api/advise/opportunities
```

**演示前检查清单**：
- [ ] Neo4j 有数据（或使用演示模式无需 Neo4j）
- [ ] 后端已启动（`--serve` 模式）
- [ ] 前端 `npm run dev` 运行中
- [ ] `Ctrl+Shift+D` 切换演示模式，圆点变绿
- [ ] 测试：选政策 → 生成申报文档 → 下载 Word 能正常打开

---

## 七、常见操作

```bash
# 查看最新抽取评估报告
ls -lt outputs/extraction/*_report.txt | head -3

# 查看最新匹配推理结果
ls -lt outputs/advisor_results/advise_*.json | head -3

# 查看推送报告
type outputs\push\push_%date:~0,4%%date:~5,2%%date:~8,2%.json

# 运行推送调度器（爬取→抽取→推送）
.venv\Scripts\python.exe -m src.ingestion.crawler.push_scheduler --run

# 测试模式（限制 PDF 数量）
.venv\Scripts\python.exe -m src.ingestion.crawler.push_scheduler --full --test
```

---

## 八、故障排查

| 现象 | 原因 | 解决方法 |
|------|------|---------|
| 匹配查询超时（>60s） | Neo4j 无 region 子节点 | 运行 `fix_region_hierarchy.py` |
| 下载 Word 打不开 | 后端没重启，返回 JSON 而非文件流 | 重启后端（`Ctrl+C` 再 `--serve`） |
| 演示模式无静态数据 | demoPolicies 未加载 | 检查 `ApplicationWorkspace.vue` 中数组 |
| `402 Insufficient Balance` | DeepSeek API 余额不足 | 充值或切换 `LLM_PROVIDER=openai` |
| Neo4j 连接失败 | Docker 未启动 | `docker start neo4j` |
| 前端页面空白 | Node 依赖未安装 | `cd FinPolicyKGFrontend && npm install` |

---

## 九、向他人分享 Neo4j 数据

### 方式一：JSON 备份文件（推荐）

```bash
# 1. 在你机器上导出
.venv\Scripts\python.exe -m src.scripts.backup_neo4j
# → 生成 data/backups/neo4j_backup_YYYYMMDD_HHMMSS.json

# 2. 把 JSON 文件发给对方

# 3. 对方导入
.venv\Scripts\python.exe -m src.scripts.restore_triplets ^
  --input data/backups/neo4j_backup_XXX.json
```

**优点**：文件小（~2.3 MB），对方用项目自带脚本一键导入。

### 方式二：Cypher 脚本导出（人类可读）

```bash
# 导出为 Cypher 语句（需要 apoc 插件）
docker exec -i neo4j cypher-shell -u neo4j -p finagent2026 ^
  "CALL apoc.export.cypher.all(null, {format: 'cypher-shell'})" ^
  > neo4j_export.cypher
```

### 方式三：Docker 容器镜像（完整克隆）

```bash
# 导出整个 Neo4j 容器
docker commit neo4j finpolicy-neo4j:backup
docker save finpolicy-neo4j:backup -o finpolicy-neo4j.tar

# 对方加载
docker load -i finpolicy-neo4j.tar
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 finpolicy-neo4j:backup
```

---

## 十、技术架构

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

### 10.1 抽取管线 — 从 PDF 到知识图谱

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

### 10.2 决策链路 — 从自然语言到政策建议

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

### 10.3 申报运营 — Phase 3 核心模块

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

## 十一、项目目录

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

## 十二、API 接口

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

## 十三、数据采集（爬虫）

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

## 十四、多 LLM 支持

通过 `.env` 中 `LLM_PROVIDER` 切换，`UniversalLLMClient` 统一适配：

| 提供商 | `LLM_PROVIDER` | 说明 |
|--------|----------------|------|
| DeepSeek（默认） | `deepseek` | `deepseek-v4-flash`，支持 reasoning_effort |
| OpenAI | `openai` | `gpt-4o` |
| 小米 MiMo | `mimo` | `mimo-v2.5-pro`，国产，无需科学上网 |

---

## 十五、已知问题与后续计划

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

---

## 十六、迁移部署指南（搬到别的电脑）

### 16.1 你需要准备什么

把项目迁到另一台电脑，需要带三样东西：

| 东西 | 文件/位置 | 大小 | 是否必须 |
|------|-----------|------|---------|
| 项目代码 | 整个 `FinPolicyKGAgent/` 目录（不含 `.venv/`） | ~10 MB | ✅ 必须 |
| 图谱数据 | `data/backups/neo4j_backup_*.json` | ~2.3 MB | ✅ 必须（否则要重抽） |
| PDF 原件（可选） | `data/raw/*.pdf` | ~100 MB | ❌ 有备份 JSON 就不用 |

---

### 16.2 打包发给对方

**在你（发送方）的机器上：**

```bash
# 1. 确认备份文件是最新的
ls data\backups\neo4j_backup_*.json

# 2. 把以下文件/目录打包成 zip
# FinPolicyKGAgent/
#   ├── src/                ← 全部代码
#   ├── config/             ← 配置文件
#   ├── data/
#   │   ├── backups/       ← 图谱备份 JSON（必须）
#   │   └── raw/          ← PDF 原件（可选）
#   ├── docker-compose.yml
#   ├── requirements.txt
#   ├── .env.template      ← 见 16.3
#   └── README.md
```

> 💡 **不要打包 `.venv/` 和 `outputs/`**——前者目标机器要重装，后者太大。

---

### 16.3 准备 `.env.template`

把你的 `.env` 复制一份，把 API Key 删掉，发给他：

```env
# .env.template（发给对方，让他另存为 .env）
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx_put_your_own_key_here   ← 让他填自己的
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=finagent2026
```

---

### 16.4 对方拿到后怎么跑起来

**在对方（接收方）的机器上：**

#### 第 1 步：安装依赖

```bash
# Python 3.13+
# 创建虚拟环境
python -m venv .venv

# 安装 Python 依赖
.venv\Scripts\activate
pip install -r requirements.txt

# Node.js 22+
# 安装前端依赖
cd FinPolicyKGFrontend
npm install
cd ..
```

#### 第 2 步：启动 Neo4j

```bash
docker run -d --name neo4j ^
  -p 7474:7474 -p 7687:7687 ^
  -e NEO4J_AUTH=neo4j/finagent2026 ^
  neo4j:5

# 等待 10 秒让 Neo4j 完全启动
# 验证：浏览器打开 http://localhost:7474
```

#### 第 3 步：恢复图谱数据（最关键）

```bash
# 从你发的备份 JSON 恢复（不需要重新抽取 PDF）
.venv\Scripts\python.exe -m src.scripts.restore_triplets ^
  --input data\backups\neo4j_backup_20260615_181917.json

# 验证恢复成功
docker exec -i neo4j cypher-shell -u neo4j -p finagent2026 ^
  "MATCH (n) RETURN count(n) AS node_count;"
# → 应返回 2753 左右
```

#### 第 4 步：启动后端

```bash
# 确认 .env 已填好 API Key
.venv\Scripts\python.exe -m src.api.main --serve

# 看到这行说明启动成功：
# 🚀 FinPolicyKG API 服务启动: http://0.0.0.0:8000
# 📚 API 文档: http://0.0.0.0:8000/docs
```

#### 第 5 步：启动前端

```bash
cd FinPolicyKGFrontend
npm run dev

# 看到这行说明启动成功：
#  Local:   http://localhost:5173/
```

打开 http://localhost:5173 即可使用。

---

### 16.5 如果没有备份 JSON（需要重抽）

```bash
# 清空 Neo4j（如果需要）
docker exec -i neo4j cypher-shell -u neo4j -p finagent2026 ^
  "MATCH (n) DETACH DELETE n;"

# 从 PDF 重新抽取（需要 DeepSeek API 余额）
.venv\Scripts\python.exe -m src.api.main ^
  --input-dir data\raw\ ^
  --workers 16
```

---

### 16.6 常见问题

| 问题 | 原因 | 解决办法 |
|------|------|---------|
| `No module named 'src'` | 没在项目根目录运行 | `cd D:\...\FinPolicyKGAgent` |
| Neo4j 连接失败 | Docker 没启动或密码不对 | `docker ps` 检查容器；核对 `.env` 密码 |
| 恢复备份时报错 | JSON 文件路径不对 | 用绝对路径，或确认文件在 `data/backups/` 下 |
| 前端连不上后端 | 后端没启动或端口被占 | 确认后端在 8000 端口；看 `vite.config.ts` 的 proxy 配置 |
| DeepSeek 402 错误 | API 余额不足 | 换 OpenAI 或充值 |

---

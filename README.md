# FinPolicyKGAgent — 实时金融政策知识图谱智能体

> 基于反思式智能体的金融政策知识图谱构建系统，从政策文档中自动抽取结构化三元组

---

## 一、项目概述

FinPolicyKGAgent 将一份金融政策 PDF，经过 **5 个阶段** 的自动化处理，最终输出结构化的知识三元组：

```
金融政策 PDF → [文档解析] → [章节分割] → [反思式抽取] → [三元组存储] → [质量评估]
                 Stage 1      Stage 2       Stage 3         Stage 4       Stage 5
```

**核心亮点**：Stage 3 采用 **提取→批判→修正** 的反思循环机制，让 LLM 自己审核自己的抽取结果，提升三元组质量。

---

## 二、技术栈

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| 文档解析 | [Docling](https://github.com/docling-project/docling) 2.91 | 开源，pip install docling，支持 PDF/DOCX/HTML |
| LLM | DeepSeek-V4-Flash | DeepSeek 官方 API，Chat Completions API，支持 reasoning_effort 推理深度控制 |
| 三元组存储 | JSON | 当前版本，后续迁移 Neo4j 图数据库 |
| 后端框架 | FastAPI | API 服务层（待完善） |
| Python | 3.13+ | |

---

## 三、项目目录结构

```
FinPolicyKGAgent/
├── config/                     # 配置
│   ├── __init__.py
│   └── settings.py             # 全局配置（自动读取 .env）
├── src/                        # 核心源码
│   ├── core/                   # 基础组件
│   │   ├── __init__.py
│   │   ├── logger.py           #   统一日志（loguru）
│   │   └── run_logger.py       #   Pipeline 运行记录器（生成 Markdown 中间产物）
│   ├── ingestion/              # 数据接入层（Stage 1-2）
│   │   ├── __init__.py
│   │   ├── parser.py           #   Docling 文档解析器
│   │   └── chunker.py          #   章节感知文本分割器
│   ├── extraction/             # 知识抽取层（Stage 3）
│   │   ├── __init__.py
│   │   ├── schema.py           #   KG Schema 定义（16实体+13关系）
│   │   ├── llm_client.py       #   DeepSeek LLM 客户端
│   │   ├── extractor.py        #   Schema 引导三元组抽取器
│   │   └── reflector.py        #   反思式智能体
│   ├── storage/                # 知识存储层（Stage 4）
│   │   ├── __init__.py
│   │   └── triplet_store.py    #   JSON 三元组存储
│   ├── evaluation/             # 评估层（Stage 5）
│   │   ├── __init__.py
│   │   └── evaluator.py        #   多维度质量评估
│   └── api/                    # API 服务层
│       ├── __init__.py
│       └── main.py             #   FastAPI 入口
├── data/                       # 数据目录
│   ├── raw/                    #   原始政策文档（PDF/DOCX）
│   ├── processed/              #   解析后中间文件
│   ├── triplets/               #   抽取的三元组 JSON
│   └── run_logs/               #   Pipeline 运行记录（Markdown）
├── reports/                    # 评估报告（HTML）
├── tests/                      # 测试（待补充）
├── logs/                       # 日志文件（按天轮转）
├── scripts/                    # 运维脚本
│   ├── run_e2e_test.py         #   端到端测试脚本
│   ├── debug_docling.py        #   Docling 调试脚本
│   ├── extract_quickstart.py   #   PDF 文本提取辅助脚本
│   └── quickstart_text.txt     #   提取后的文本缓存
├── test_api.py                 #   API 连通性快速测试
├── .env                        # 环境变量（API Key 等，不提交 Git）
├── .env.example                # 环境变量模板
├── .gitignore
├── pyproject.toml              # 项目元数据
├── requirements.txt            # Python 依赖
└── README.md                   # 本文件
```

---

## 四、各模块详细说明

### 4.1 配置层 — `config/settings.py`

全局配置，自动从 `.env` 文件加载环境变量。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DEEPSEEK_API_KEY` | `your_api_key_here` | DeepSeek API Key |
| `DOUBAO_API_KEY` | `your_api_key_here` | 兼容旧字段（已废弃，保留以兼容 .env） |
| `DOUBAO_BASE_URL` | `https://api.deepseek.com` | API 地址（兼容旧字段名，实际指向 DeepSeek） |
| `DOUBAO_MODEL` | `deepseek-v4-flash` | 模型名称（兼容旧字段名） |
| `APP_ENV` | `development` | 运行环境 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

路径配置（自动计算，无需手动设置）：

| 配置项 | 路径 |
|--------|------|
| `RAW_DIR` | `data/raw/` |
| `PROCESSED_DIR` | `data/processed/` |
| `TRIPLETS_DIR` | `data/triplets/` |
| `RUN_LOGS_DIR` | `data/run_logs/` |
| `LOGS_DIR` | `logs/` |

### 4.1.1 Pipeline 运行记录器 — `src/core/run_logger.py`

**核心类**：`PipelineRunLogger`

**功能**：每次运行 Pipeline 生成一个 Markdown 文件，记录所有阶段的中间产物（解析全文、Chunk 详情、迭代日志、评估报告等）。

**输出路径**：`data/run_logs/{source_file}_{timestamp}.md`

**记录阶段**：

| 方法 | 记录内容 |
|------|---------|
| `log_stage1_input()` | 输入文件信息（文件名、大小、类型） |
| `log_stage1_output()` | 解析结果（标题、章节数、全文 Markdown） |
| `log_stage2_input()` | 分割前信息 |
| `log_stage2_output()` | 每个 Chunk 详情（文本、token 估算） |
| `log_stage3_summary()` | 反思迭代摘要 + 最终三元组表格 + 迭代日志 |
| `log_stage4_output()` | 存储统计（实体/关系类型分布） |
| `log_stage5_output()` | 完整评估报告 |

---

### 4.2 Stage 1：文档解析 — `src/ingestion/parser.py`

**核心类**：`DoclingParser`

**功能**：将 PDF/DOCX/HTML 解析为结构化文本，保留章节层级。

**章节识别策略**（三优先级）：
1. Docling label 识别（`title`/`section_header`）
2. 中文条款编号模式识别（`一、`/`（一）`/`第一条`）← 政策 PDF 常用
3. 兜底：全文作为一个章节

**输入输出**：

```
输入: file_path (PDF/DOCX/HTML 路径)
输出: ParsedDocument
  ├── source_file: 文件名
  ├── title: 文档标题
  ├── doc_type: 文件类型
  ├── sections: [{heading, level, content}, ...]
  ├── full_text: 完整 Markdown 文本
  └── metadata: {num_sections, char_count}
```

**主要方法**：

| 方法 | 说明 |
|------|------|
| `parse(file_path) → ParsedDocument` | 解析单个文档 |
| `parse_and_save(file_path) → ParsedDocument` | 解析并保存结果 |
| `parse_batch(dir_path) → list[ParsedDocument]` | 批量解析目录 |

---

### 4.3 Stage 2：章节感知分割 — `src/ingestion/chunker.py`

**核心类**：`SectionAwareChunker`

**功能**：按文档逻辑边界拆分，保持段落主题连贯性。

**分块参数**：

| 参数 | 值 | 说明 |
|------|---|------|
| `MIN_TOKENS` | 200 | 过短则与相邻段落合并 |
| `TARGET_TOKENS` | 600 | 目标长度 |
| `MAX_TOKENS` | 1024 | 超过则按句号/分号进一步切分 |

**分割策略**：
1. 先按章节边界拆分
2. 章节内按条款编号（`第一条`、`（一）`、`1、`等）进一步拆分
3. 过短的段落（< 200 tokens）与同章节上一个 chunk 合并
4. 过长的段落（> 1024 tokens）按句子切分

**输入输出**：

```
输入: ParsedDocument
输出: ChunkedDocument
  ├── source_file: 文件名
  ├── policy_id: 政策文号（如"银发〔2025〕123号"）
  ├── publish_date: 发布日期
  ├── chunks: [Chunk, ...]
  │     ├── chunk_id: "chunk_001"
  │     ├── text: 文本内容
  │     ├── heading: 所属章节标题
  │     ├── chapter_idx: 章节序号
  │     ├── section_idx: 段落序号
  │     └── token_count: 估算 token 数
  └── save() → 保存为 JSON
```

**主要方法**：

| 方法 | 说明 |
|------|------|
| `chunk(parsed_doc) → ChunkedDocument` | 对解析后文档进行分块 |
| `_split_by_clauses(text) → list[str]` | 按条款边界拆分 |
| `_split_long_chunk(chunk) → list[Chunk]` | 过长 chunk 按句子切分 |

---

### 4.4 Stage 3a：KG Schema — `src/extraction/schema.py`

定义知识图谱的"骨架"——允许哪些实体和关系。

**实体类型**（16 种）：

| 类型 | 中文 | 层级 |
|------|------|------|
| Policy | 政策 | 顶级 |
| MonetaryPolicy | 货币政策 | → Policy 子类 |
| FiscalPolicy | 财政政策 | → Policy 子类 |
| RegulatoryPolicy | 监管政策 | → Policy 子类 |
| Institution | 机构 | 顶级 |
| FinancialConcept | 金融概念 | 顶级 |
| InterestRate | 利率 | → FinancialConcept 子类 |
| ReserveRatio | 准备金率 | → FinancialConcept 子类 |
| TaxRate | 税率 | → FinancialConcept 子类 |
| Quota | 配额 | → FinancialConcept 子类 |
| Market | 市场 | → FinancialConcept 子类 |
| Instrument | 工具 | → FinancialConcept 子类 |
| Event | 事件 | 顶级 |
| Indicator | 指标 | 顶级 |
| Person | 人物 | 顶级 |
| Document | 文档 | 顶级 |

**关系类型**（13 种）：

| 关系 | 中文 | 方向约束 |
|------|------|---------|
| issues | 发布 | Institution → Policy |
| modifies | 修订 | Policy → Policy |
| repeals | 废止 | Policy → Policy |
| affects | 影响 | Policy → FinancialConcept 等 |
| sets | 设定值 | Policy → Indicator 等 |
| targets | 针对 | Policy → Market/Institution |
| references | 引用 | Policy → Policy |
| cites_as_basis | 依据 | Policy → Policy |
| leads_to | 导致 | Event → Event |
| mentions | 提及 | Document → Entity |
| has_indicator | 含指标 | Policy → Indicator |
| valid_during | 有效期 | Policy → TimeInterval |
| similar_to | 相似 | Policy → Policy |

**Schema 校验**：每个三元组都会经过 `Triple.validate()` 校验，检查关系类型是否合法、主语/宾语类型是否匹配约束。不合规的三元组会被自动过滤。

---

### 4.5 Stage 3b：LLM 客户端 — `src/extraction/llm_client.py`

**核心类**：`DeepSeekClient`

**功能**：通过 DeepSeek API 调用 deepseek-v4-flash，支持 reasoning_effort 和思维链。

**调用方式**：

```python
# 使用 OpenAI SDK 兼容模式
client = OpenAI(api_key=..., base_url="https://api.deepseek.com")

# Chat Completions API
response = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    reasoning_effort="medium",    # 推理深度：low / medium / high
    max_tokens=8192,
)
# 注意：reasoning 模型不支持 temperature 参数，自动跳过
```

**容错机制**：

| 机制 | 说明 |
|------|------|
| 自动重试 | 最多 3 次，指数退避（3s→6s→12s） |
| 空响应处理 | 重试后仍为空则返回兜底空结构 |
| Markdown 清理 | 自动去除 ` ```json ``` ` 包裹 |
| 截断 JSON 修复 | 自动补齐括号，尝试恢复部分数据 |
| 最终兜底 | 所有解析失败返回 `{"entities": [], "triples": []}` |

**主要方法**：

| 方法 | 说明 |
|------|------|
| `chat(system_prompt, user_prompt) → str` | 调用 LLM，返回文本 |
| `chat_json(system_prompt, user_prompt) → dict` | 调用 LLM，返回解析后的 JSON |

---

### 4.6 Stage 3c：Schema 引导抽取 — `src/extraction/extractor.py`

**核心类**：`SchemaGuidedExtractor`

**功能**：将 Schema 定义注入 LLM Prompt，在闭域内抽取结构化三元组。

**工作流程**：

```
1. 构造 Schema 引导 Prompt（包含实体类型、关系类型、约束规则）
2. 调用 LLM 生成 JSON 格式的三元组
3. 解析 LLM 输出的 entities 和 triples
4. Schema 校验：过滤不合规三元组
```

**抽取规则**（注入 Prompt）：
- 只抽取文本中明确提及的实体和关系，不推测
- 实体名称使用原文表述
- 区分政策语义："鼓励" ≠ "强制"、"原则上" ≠ "必须"

**主要方法**：

| 方法 | 说明 |
|------|------|
| `extract(chunk, existing_entities?) → (entities, triples)` | 从单个 chunk 抽取三元组 |

---

### 4.7 Stage 3d：反思式智能体 — `src/extraction/reflector.py`

**核心类**：`ReflectiveAgent`

**功能**：执行 **提取→批判→修正** 的循环迭代，直至收敛。

**反思流程**：

```
Round 0: 初始抽取（SchemaGuidedExtractor）
    ↓
Round 1: 批判（LLM 从 4 个维度审核）
    ├── passed → 收敛，结束
    └── 未通过 → 修正（LLM 根据反馈修正）→ 计算变更率
        ├── 变更率 < 5% → 收敛，结束
        └── 变更率 ≥ 5% → 进入 Round 2
    ↓
Round 2: 再次批判 → ...（最多 3 轮）
```

**批判维度**：
1. **完整性**：是否有遗漏的实体或关系？
2. **准确性**：关系方向和类型是否正确？
3. **一致性**：是否存在自相矛盾的三元组？
4. **政策语义**：是否误读了政策表述？

**收敛条件**（满足任一即停止）：
- 批判 LLM 输出 `passed: true`
- 三元组变更率 < 5%
- 达到最大迭代次数（3 轮）

**输入输出**：

```
输入: Chunk + 已有实体上下文
输出: ReflectionResult
  ├── entities: 最终实体列表
  ├── triples: 最终三元组列表
  ├── iterations: 实际迭代轮次
  ├── converged: 是否收敛
  └── iteration_log: 每轮详细日志
```

**主要方法**：

| 方法 | 说明 |
|------|------|
| `extract_with_reflection(chunk) → ReflectionResult` | 反思式抽取（核心方法） |
| `_critique(chunk, triples) → dict` | 批判阶段 |
| `_revise(chunk, entities, triples, critique) → (entities, triples)` | 修正阶段 |
| `_compute_change_rate(old, new) → float` | 计算变更率 |

---

### 4.8 Stage 4：三元组存储 — `src/storage/triplet_store.py`

**核心类**：`TripletStore`

**功能**：三元组的 JSON 格式存储，支持添加、去重、统计、合并。

**存储格式**：

```json
{
  "source_file": "中国人民银行公告〔2026〕第10号.pdf",
  "policy_id": "（银办发〔2016〕112号）",
  "extract_time": "2026-04-26T03:30:56",
  "entities": [
    {"name": "中国人民银行", "type": "Institution", "attributes": {}, "source_chunk_id": "chunk_001"}
  ],
  "triples": [
    {
      "subject": {"name": "中国人民银行", "type": "Institution"},
      "relation": "issues",
      "object": {"name": "中国人民银行公告〔2026〕第10号", "type": "Policy"},
      "confidence": 1.0,
      "source_text": "中国人民银行公告〔2026〕第10号"
    }
  ],
  "stats": {
    "total_entities": 7,
    "total_triples": 4,
    "entity_type_distribution": {"Institution": 2, "Policy": 5},
    "relation_type_distribution": {"issues": 1, "modifies": 1, "repeals": 2}
  }
}
```

**主要方法**：

| 方法 | 说明 |
|------|------|
| `add_entities(entities) → int` | 添加实体（按 name+type 去重） |
| `add_triples(triples) → int` | 添加三元组（按 主语+关系+宾语 去重） |
| `compute_stats() → dict` | 计算统计信息 |
| `save(output_path?) → Path` | 保存为 JSON |
| `load(path) → TripletStore` | 从 JSON 加载 |
| `merge(other) → dict` | 合并另一个 store（去重） |

---

### 4.9 Stage 5：四层一体化评估 — `src/evaluation/evaluator.py`

**核心类**：`Evaluator`（统一入口，编排 4 个子评估器）

**功能**：从规则合规、抽取效率、语义多样性、LLM 裁判四个层级递进评估抽取质量。

**四层评估架构**：

```
┌─────────────────────────────────────────────────┐
│  L1: CheckRules（规则合规性）                     │
│  4 条强制规则，逐条检查每条三元组                   │
├─────────────────────────────────────────────────┤
│  L2: Local Extraction Efficiency（本地抽取效率）   │
│  覆盖率指标，衡量 Schema 利用程度                   │
├─────────────────────────────────────────────────┤
│  L3: Global Semantic Diversity（全局语义多样性）   │
│  熵度量，衡量类型分布的均匀性                       │
├─────────────────────────────────────────────────┤
│  L4: LLM-as-a-Judge（大模型裁判）                  │
│  4 维度打分，衡量语义层面的抽取质量                  │
└─────────────────────────────────────────────────┘
```

#### L1: CheckRules — 规则合规性

**评估器**：`CheckRulesEvaluator`

**4 条强制规则**（全部通过才算完全合规）：

| 规则 | 说明 | 示例（违规） |
|------|------|-------------|
| R1 主体引用明确 | 不允许模糊指代（"本公司""该行""我行"等） | `该公司 → issues → 政策A` |
| R2 实体长度≤15字符 | 实体名称不超过 15 个字符 | `关于进一步规范金融机构…的通知` |
| R3 实体类型合规 | 必须属于预定义 Schema 的 16 种实体类型 | `type: "Unknown"` |
| R4 关系类型合规 | 必须属于预定义 Schema 的 13 种关系类型 | `relation: "belongs_to"` |

**输出**：完全合规率（满足全部 4 条规则的三元组占比）+ 各规则违规数 + 逐条详情。

#### L2: Local Extraction Efficiency — 本地抽取效率

**评估器**：`LocalEfficiencyEvaluator`

**5 个覆盖率指标**：

| 指标 | 全称 | 公式 | 说明 |
|------|------|------|------|
| ECR | Entity Coverage Rate | 有关系的实体数 / 总实体数 | 实体利用率 |
| TCR | Type Coverage Rate | 出现的实体类型数 / 16 | Schema 实体类型覆盖 |
| RCR | Relation Coverage Rate | 出现的关系类型数 / 13 | Schema 关系类型覆盖 |
| TCR-N | Normalized Type Coverage | 去重层级后的基础类型覆盖率 | 考虑父子类型归并 |
| RCR-N | Normalized Relation Coverage | 有效关系类型覆盖率 | 排除空约束关系 |

附加：`avg_triples_per_chunk`（每块平均三元组数）。

#### L3: Global Semantic Diversity — 全局语义多样性

**评估器**：`SemanticDiversityEvaluator`

**3 种熵度量**（实体和关系各一组）：

| 熵类型 | 公式 | 说明 |
|--------|------|------|
| Shannon 熵 | H = -Σ p_i·log₂(p_i) | 类型分布的不确定性 |
| Schema 归一化熵 | H / log₂(Schema类型数) | 归一化到 [0,1]，1 = 均匀分布 |
| Rényi 熵 (α=2) | H₂ = -log₂(Σ p_i²) | 碰撞熵，更敏感于集中分布 |

- 值越大 → 类型分布越均匀 → 多样性越好
- 值越小 → 类型集中在少数几种 → 多样性不足

#### L4: LLM-as-a-Judge — 大模型裁判

**评估器**：`LLMJudgeEvaluator`

**4 个评分维度**（LLM 打 0-10 分，归一化到 [0,1]）：

| 维度 | 说明 |
|------|------|
| Precision（精确性） | 实体是否清晰、唯一、无歧义？关系是否精确？ |
| Faithfulness（忠实度） | 三元组是否忠实于原文事实？有无编造或歪曲？ |
| Comprehensiveness（完整性） | 是否抽取了原文中的关键实体和关系？有无遗漏？ |
| Relevance（相关性） | 三元组是否与金融政策主题相关？有无噪声？ |

- 综合得分 = 4 项均值
- 需要 LLM 客户端（DeepSeek），可通过 `enable_llm_judge=False` 关闭
- 评估时会传入原文（截断至 3000 字）+ 三元组 JSON

**输出示例**：

```
═══════════════════════════════════════════════════
  FinPolicyKG 四层一体化评估报告
═══════════════════════════════════════════════════
文档: 中国人民银行公告〔2026〕第10号.pdf
实体: 70  三元组: 21  置信度: 1.00

【L1: CheckRules 规则合规性】
  完全合规率: 28.6% (6/21)
  规则1 主体引用明确: 0 违规
  规则2 实体长度≤15字符: 15 违规
  规则3 实体类型合规: 0 违规
  规则4 关系类型合规: 0 违规

【L2: Local Extraction Efficiency 本地抽取效率】
  每块平均三元组数: 2.10
  ECR 实体覆盖率: 37.1%
  TCR 实体类型覆盖率: 43.8%
  RCR 关系覆盖率: 38.5%
  TCR-N 归一化类型覆盖率: 57.1%
  RCR-N 归一化关系覆盖率: 41.7%

【L3: Global Semantic Diversity 全局语义多样性】
  香农熵(实体): 2.3990
  香农熵(关系): 2.2438
  Schema归一化熵(实体): 0.5998
  Schema归一化熵(关系): 0.6064
  Rényi熵(实体, α=2): 2.1553
  Rényi熵(关系, α=2): 2.1847

【L4: LLM-as-a-Judge 大模型裁判】
  精确性 Precision:       0.50
  忠实度 Faithfulness:     0.70
  完整性 Comprehensiveness: 0.40
  相关性 Relevance:        0.90
  综合得分:                0.62

【反思效率】
  迭代轮次: 1
  是否收敛: 是
═══════════════════════════════════════════════════
```

**主要方法**：

| 方法 | 说明 |
|------|------|
| `Evaluator.evaluate(store, reflection_result?, num_chunks?, source_text?, enable_llm_judge?) → EvaluationReport` | 执行四层评估 |
| `EvaluationReport.to_text() → str` | 生成可读报告文本 |

---

## 五、快速开始

### 5.1 环境准备

```bash
# 1. 进入项目目录
cd D:\桌面\agent实验室项目\finagent\FinPolicyKGAgent

# 2. 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. 安装依赖
pip install -r requirements.txt
```

### 5.2 配置 API Key

```bash
# 复制模板
copy .env.example .env

# 编辑 .env，填入你的 DeepSeek API Key
# DEEPSEEK_API_KEY=你的真实Key
```

### 5.3 运行端到端测试

```bash
# 命令行方式
.venv\Scripts\python.exe scripts\run_e2e_test.py

# 或在 PyCharm 中：
# 1. 配置解释器 → .venv\Scripts\python.exe
# 2. 右键 run_e2e_test.py → Run
```

### 5.4 查看结果

- **运行日志**：PyCharm 底部 Run 窗口
- **三元组 JSON**：`data/triplets/` 目录下

---

## 六、数据流图

```
┌─────────────┐     ┌──────────────┐     ┌───────────────────┐
│  金融政策    │     │  Docling     │     │  章节感知分割器    │
│  PDF 文档    │────▶│  文档解析器   │────▶│  SectionAware     │
│             │     │  DoclingParser│     │  Chunker          │
└─────────────┘     └──────────────┘     └─────────┬─────────┘
                                                    │
                                          ParsedDocument → ChunkedDocument
                                                    │
                                                    ▼
┌─────────────┐     ┌──────────────┐     ┌───────────────────┐
│  评估报告    │     │  三元组存储   │     │  反思式智能体      │
│  Evaluation │◀────│  TripletStore│◀────│  ReflectiveAgent  │
│  Report     │     │  (JSON)      │     │  ┌─────────────┐  │
└─────────────┘     └──────────────┘     │  │ 抽取→批判→修正│  │
                                          │  └─────────────┘  │
                                          └───────────────────┘
                                                    │
                                          DeepSeek LLM
```

---

## 七、当前状态与后续计划

| 功能 | 状态 | 说明 |
|------|------|------|
| Docling 文档解析 | ✅ 已完成 | 含政策 PDF 条款编号识别 |
| 章节感知分割 | ✅ 已完成 | 200-1024 token 智能分块 |
| Schema 定义 | ✅ 已完成 | 16 实体 + 13 关系 + 约束校验 |
| LLM 三元组抽取 | ✅ 已完成 | Schema 引导 + 闭域抽取 |
| 反思式智能体 | ✅ 已完成 | 提取→批判→修正，自动收敛 |
| JSON 三元组存储 | ✅ 已完成 | 去重、统计、合并 |
| 四层一体化评估 | ✅ 已完成 | L1 CheckRules + L2 覆盖率 + L3 语义多样性 + L4 LLM-as-Judge |
| Neo4j 图数据库 | 🔜 待开发 | 替换 JSON 存储，支持图查询 |
| FastAPI 服务 | 🔜 待开发 | RESTful API 接口 |
| 实时更新机制 | 🔜 待开发 | 监控政策网站，自动触发 Pipeline |
| KG-RAG 检索 | 🔜 待开发 | 自然语言→Cypher 查询 |

**已知问题**（2026-05-02 核实，DeepSeek-V4-Flash，10 chunk，70 实体，21 三元组）：

| 问题 | 优先级 | 位置 | 说明 |
|------|--------|------|------|
| 修正阶段变量名错误 | ✅ 已修复 | `reflector.py:272` | `new_entities` → `entities`，修正阶段现已正常工作 |
| `references` 关系约束过严 | 🟡 P1 | `schema.py:93` | 只允许 Policy→Policy，导致 Chunk 4/10 过滤 15 条合法三元组（如 Policy→InterestRate 的引用关系被拒绝） |
| 修正阶段 LLM 返回格式异常 | 🟡 P1 | `reflector.py:234-238` | LLM 偶发返回 list 而非 dict，代码已做防御适配（自动包装为 `{"entities": [], "triples": result}`），但修正后的三元组仍可能不合规 |
| L1 R2 实体长度规则过严 | 🟡 P1 | `evaluator.py` | R2 规则限制实体名称≤15字符，但金融政策实体天然偏长（如政策全称、条款原文），导致 71.4% 三元组被判违规。需考虑放宽阈值或区分实体类型 |
| JSON 解析偶发异常 | 🟢 P2 | `llm_client.py` | DeepSeek 偶发输出双大括号 `{{` 或截断，已通过 `_repair_truncated_json()` 自动修复 |
| llm_client 注释残留 | ✅ 已修复 | `llm_client.py` | `Doubao` 注释已全部替换为 `DeepSeek` |
| main.py L4 评估未传 LLM 客户端 | ✅ 已修复 | `src/api/main.py:91` | `Evaluator()` → `Evaluator(llm_client=get_llm_client())`，L4 评分现已正常输出 |
| 429 限流未优雅处理 | ✅ 已解决 | — | 安全体验模式触发后程序崩溃（已修复） |

**Bug 影响链路分析**：

```
✅ P0（已修复）: reflector.py:272 new_entities → entities
   修正阶段现已正常工作，反思循环"抽取→批判→修正"完整执行

P1: schema.py references 约束 Policy→Policy
 └─→ LLM 抽取的 Policy→FinancialConcept 引用关系被 validate() 过滤
      └─→ 15 条合法三元组丢失
           └─→ 抽取覆盖率下降

P1: R2 实体长度≤15字符
 └─→ 政策全称、条款原文天然>15字符
      └─→ 71.4% 三元组被判违规
           └─→ L1 合规率虚低，评估指标失真

✅ P2（已修复）: main.py L4 未传 llm_client
   Evaluator(llm_client=get_llm_client())，L4 评分现已正常输出
```

**L1 评估详情**（21 三元组，6 合规，15 违规）：

| 规则 | 结果 | 备注 |
|------|------|------|
| R1 主体引用明确 | 0 违规 ✅ | |
| R2 实体长度≤15字符 | **15 违规**（占 71.4%） | 多为政策条款原文作实体名，规则阈值可能需放宽（P1） |
| R3 实体类型合规 | 0 违规 ✅ | |
| R4 关系类型合规 | 0 违规 ✅ | |

**L4 评审摘要**：实体清晰度不足（长字符串作实体）；存在编造实体（"关于修改...的决定"）；完整性遗漏多处具体修改；相关性 0.90 无噪声。

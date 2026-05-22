"""
金融政策知识图谱 Schema 定义
定义允许的实体类型、关系类型及其约束

对应设计文档 Section 3.1.2 的 Ontology Schema
"""

from enum import Enum
from dataclasses import dataclass, field


# ══════════════════════════════════════════
# 实体类型定义
# ══════════════════════════════════════════

class EntityType(str, Enum):
    """金融政策领域实体类型"""
    POLICY = "Policy"                      # 政策
    MONETARY_POLICY = "MonetaryPolicy"     # 货币政策
    FISCAL_POLICY = "FiscalPolicy"         # 财政政策
    REGULATORY_POLICY = "RegulatoryPolicy" # 监管政策
    INSTITUTION = "Institution"            # 机构
    FINANCIAL_CONCEPT = "FinancialConcept" # 金融概念
    INTEREST_RATE = "InterestRate"         # 利率
    RESERVE_RATIO = "ReserveRatio"         # 准备金率
    TAX_RATE = "TaxRate"                   # 税率
    QUOTA = "Quota"                        # 配额
    MARKET = "Market"                      # 市场
    INSTRUMENT = "Instrument"              # 工具
    EVENT = "Event"                        # 事件
    INDICATOR = "Indicator"                # 指标
    PERSON = "Person"                      # 人物
    DOCUMENT = "Document"                  # 文档
    # ── 决策支持扩展实体 ──
    ACTION_TYPE = "ActionType"             # 措施大类（6选1）
    CONDITION = "Condition"                # 适用条件（标准化枚举）
    STRATEGY = "Strategy"                  # 策略（规则生成）
    REGION = "Region"                      # 地区节点（层级）
    COMPANY_TYPE = "CompanyType"           # 企业类型枚举
    INDUSTRY = "Industry"                  # 行业枚举


# 实体类型层级（子类 → 父类）
ENTITY_HIERARCHY: dict[str, str] = {
    "MonetaryPolicy": "Policy",
    "FiscalPolicy": "Policy",
    "RegulatoryPolicy": "Policy",
    "InterestRate": "FinancialConcept",
    "ReserveRatio": "FinancialConcept",
    "TaxRate": "FinancialConcept",
    "Quota": "FinancialConcept",
    "Market": "FinancialConcept",
    "Instrument": "FinancialConcept",
}


# 实体类型 → 允许的属性
ENTITY_ATTRIBUTES: dict[str, list[str]] = {
    "Policy": ["policy_id", "title", "issuing_body", "effective_date", "expiry_date", "status", "level"],
    "Institution": ["name", "type", "jurisdiction"],
    "FinancialConcept": ["name", "description"],
    "InterestRate": ["name", "value", "unit", "change"],
    "ReserveRatio": ["name", "value", "unit", "change"],
    "Event": ["event_type", "timestamp", "impact_scope"],
    "Indicator": ["name", "value", "unit", "period", "source"],
    "Person": ["name", "title", "institution"],
    "Document": ["url", "publish_date", "content_hash"],
    # ── 决策支持扩展属性 ──
    "ActionType": ["category", "raw"],         # category=6大类, raw=原始短语列表
    "Condition": ["category", "value"],         # category=region/company_type/industry
    "Strategy": ["name", "description"],
    "Region": ["name", "level"],                # level=市/省/国
    "CompanyType": ["name"],
    "Industry": ["name"],
}


# ══════════════════════════════════════════
# 决策支持：Action 6 大类定义
# ══════════════════════════════════════════

ACTION_CATEGORIES: dict[str, list[str]] = {
    "融资类": ["贷款", "信贷", "授信", "融资", "再贷款", "贴息"],
    "财政类": ["补贴", "资金支持", "奖补", "资助", "拨款", "专项资金"],
    "税收类": ["减税", "免税", "退税", "税收优惠", "税收减免", "加计扣除"],
    "风险类": ["担保", "增信", "保险", "风险补偿", "信用保证"],
    "投资类": ["基金", "投资支持", "股权投资", "创业投资", "产业基金"],
    "人才类": ["人才引进", "培训", "人才补贴", "人才公寓", "落户"],
}

# Action 原始短语 → 6 大类映射（反向索引，由 ACTION_CATEGORIES 自动生成）
ACTION_KEYWORD_MAP: dict[str, str] = {}
for _cat, _keywords in ACTION_CATEGORIES.items():
    for _kw in _keywords:
        ACTION_KEYWORD_MAP[_kw] = _cat


# ══════════════════════════════════════════
# 决策支持：Condition 标准化枚举
# ══════════════════════════════════════════

CONDITION_ENUMS: dict[str, list[str]] = {
    "company_type": [
        "中小企业", "小微企业", "大型企业", "国有企业", "民营企业",
        "外资企业", "高新技术企业", "专精特新企业", "上市公司",
    ],
    "industry": [
        "制造业", "信息技术", "金融服务", "生物医药", "新能源",
        "新材料", "现代农业", "文化创意", "商贸流通", "建筑业",
        "交通运输", "房地产", "教育", "医疗健康",
    ],
    # region 不用枚举，用层级节点 + subregion_of
}

# Region 层级定义（子 → 父链）
REGION_HIERARCHY: dict[str, str] = {
    "深圳": "广东",
    "广东": "中国",
    "北京": "中国",
    "上海": "中国",
    "广州": "广东",
    "杭州": "浙江",
    "浙江": "中国",
    "江苏": "中国",
    "成都": "四川",
    "四川": "中国",
}


# ══════════════════════════════════════════
# 决策支持：Strategy 规则映射
# ══════════════════════════════════════════

ACTION_TO_STRATEGIES: dict[str, list[str]] = {
    "融资类": ["扩大融资能力", "扩产"],
    "财政类": ["降低成本", "增加投入"],
    "税收类": ["提高利润"],
    "风险类": ["降低融资门槛"],
    "投资类": ["扩张业务"],
    "人才类": ["提升能力"],
}


# ══════════════════════════════════════════
# 关系类型定义
# ══════════════════════════════════════════

class RelationType(str, Enum):
    """金融政策领域关系类型"""
    ISSUES = "issues"               # 发布：Institution → Policy
    MODIFIES = "modifies"           # 修订：Policy → Policy
    REPEALS = "repeals"             # 废止：Policy → Policy
    AMENDS = "amends"               # 修订替代：Policy → Policy
    AFFECTS = "affects"             # 影响：Policy → FinancialConcept
    SETS = "sets"                   # 设定值：Policy → Indicator
    TARGETS = "targets"             # 针对：Policy → Market/Institution
    REFERENCES = "references"       # 引用：Policy → Policy
    CITES_AS_BASIS = "cites_as_basis"  # 依据：Policy → Policy
    LEADS_TO = "leads_to"           # 导致：Event→Event / ActionType→Strategy
    MENTIONS = "mentions"           # 提及：Document → Entity
    HAS_INDICATOR = "has_indicator" # 含指标：Policy → Indicator
    VALID_DURING = "valid_during"   # 有效期：Policy → TimeInterval
    SIMILAR_TO = "similar_to"       # 相似：Policy → Policy
    # ── 决策支持扩展关系 ──
    PROVIDES = "provides"               # 提供：Policy → ActionType
    HAS_ELIGIBILITY = "has_eligibility" # 适用条件：Policy → Condition
    SUBREGION_OF = "subregion_of"       # 子区域：Region → Region


# 关系约束（主语类型 → 关系 → 宾语类型）
RELATION_CONSTRAINTS: dict[str, tuple[list[str], list[str]]] = {
    "issues":         (["Institution"], ["Policy"]),
    "modifies":       (["Policy"], ["Policy"]),
    "repeals":        (["Policy"], ["Policy"]),
    "affects":        (["Policy"], ["FinancialConcept", "Market", "InterestRate", "ReserveRatio"]),
    "sets":           (["Policy"], ["Indicator", "InterestRate", "ReserveRatio"]),
    "targets":        (["Policy"], ["Market", "Institution"]),
    "references":     (["Policy"], ["Policy"]),
    "cites_as_basis": (["Policy"], ["Policy"]),
    "leads_to":       (["Event", "ActionType"], ["Event", "Strategy"]),  # 扩展：ActionType→Strategy
    "mentions":       (["Document"], ["Policy", "Institution", "FinancialConcept"]),
    "has_indicator":  (["Policy"], ["Indicator"]),
    "valid_during":   (["Policy"], []),
    "similar_to":     (["Policy"], ["Policy"]),
    # ── 决策支持扩展约束 ──
    "provides":        (["Policy"], ["ActionType"]),
    "has_eligibility": (["Policy"], ["Condition"]),
    "subregion_of":    (["Region"], ["Region"]),
    # ── 时序化扩展约束 ──
    "amends":          (["Policy"], ["Policy"]),  # 修订：A政策修订B政策
}


# ══════════════════════════════════════════
# 校验结果结构
# ══════════════════════════════════════════

@dataclass
class ValidationIssues:
    """三元组校验结果（替代原有的 list[str]）

    使用结构化标记而非纯文本描述，方便下游分级处理器做精确判定。
    """
    relation_unknown: bool = False           # 关系类型不在 RELATION_CONSTRAINTS
    head_type_mismatch: bool = False         # 头实体类型不匹配
    tail_type_mismatch: bool = False         # 尾实体类型不匹配
    entity_length_exceeded: bool = False     # 实体名过长
    relation_constraint_violation: bool = False  # 关系约束违反（如方向错误）
    details: list[str] = field(default_factory=list)  # 可读描述

    def has_any(self) -> bool:
        """是否存在任何校验问题"""
        return (self.relation_unknown or self.head_type_mismatch
                or self.tail_type_mismatch or self.entity_length_exceeded
                or self.relation_constraint_violation)

    def to_list(self) -> list[str]:
        """兼容旧代码：转回 list[str] 格式"""
        return self.details


# ══════════════════════════════════════════
# 三元组数据结构
# ══════════════════════════════════════════

@dataclass
class Entity:
    """实体"""
    name: str                           # 实体名称
    entity_type: str                    # 实体类型
    attributes: dict = field(default_factory=dict)  # 属性键值对
    source_chunk_id: str = ""           # 来源 chunk ID

    def validate_type(self) -> bool:
        """校验实体类型是否合法"""
        try:
            EntityType(self.entity_type)
            return True
        except ValueError:
            # 检查层级中的子类
            return self.entity_type in ENTITY_HIERARCHY


@dataclass
class Triple:
    """三元组：主语 - 关系 - 宾语"""
    subject: Entity                     # 主语实体
    relation: str                       # 关系类型
    object_: Entity                     # 宾语实体
    confidence: float = 1.0             # 置信度 [0, 1]
    source_text: str = ""               # 原文依据
    source_chunk_id: str = ""           # 来源 chunk
    source_sentence_index: int = -1     # 原文句子编号（1-based，-1 表示未标注）
    # ── 本体治理层新增字段 ──
    raw_relation: str = ""              # 弱归一：保留归一化前的原始关系名（如 "补贴"）
    source: str = "extraction"          # 来源标记：extraction / normalized / auto_promoted / pool_backfill / truncated
    raw_head: str = ""                  # PASS_TRUNCATED：保留截断前的原始主语名
    raw_tail: str = ""                  # PASS_TRUNCATED：保留截断前的原始宾语名

    def validate(self) -> ValidationIssues:
        """校验三元组是否符合 Schema 约束，返回结构化校验结果"""
        issues = ValidationIssues()

        # 校验关系类型
        try:
            RelationType(self.relation)
        except ValueError:
            issues.relation_unknown = True
            issues.details.append(f"未知关系类型: {self.relation}")
            # 未知关系时，类型约束无法检查，直接返回
            return issues

        # 校验主语/宾语类型约束
        if self.relation in RELATION_CONSTRAINTS:
            subj_types, obj_types = RELATION_CONSTRAINTS[self.relation]
            if subj_types and self.subject.entity_type not in subj_types:
                # 检查层级父类
                parent = ENTITY_HIERARCHY.get(self.subject.entity_type)
                if parent not in subj_types:
                    issues.head_type_mismatch = True
                    issues.details.append(
                        f"关系 {self.relation} 主语应为 {subj_types}，"
                        f"实际为 {self.subject.entity_type}"
                    )
            if obj_types and self.object_.entity_type not in obj_types:
                parent = ENTITY_HIERARCHY.get(self.object_.entity_type)
                if parent not in obj_types:
                    issues.tail_type_mismatch = True
                    issues.details.append(
                        f"关系 {self.relation} 宾语应为 {obj_types}，"
                        f"实际为 {self.object_.entity_type}"
                    )

        return issues

    def to_dict(self) -> dict:
        """转为字典格式"""
        d = {
            "subject": {"name": self.subject.name, "type": self.subject.entity_type},
            "relation": self.relation,
            "object": {"name": self.object_.name, "type": self.object_.entity_type},
            "confidence": self.confidence,
            "source_text": self.source_text,
            "source_chunk_id": self.source_chunk_id,
            "source": self.source,
        }
        if self.source_sentence_index >= 0:
            d["source_sentence_index"] = self.source_sentence_index
        if self.raw_relation:
            d["raw_relation"] = self.raw_relation
        if self.raw_head:
            d["raw_head"] = self.raw_head
        if self.raw_tail:
            d["raw_tail"] = self.raw_tail
        return d


# ══════════════════════════════════════════
# Schema Prompt 注入文本
# ══════════════════════════════════════════

SCHEMA_PROMPT = """【允许的实体类型】
Policy（政策）, MonetaryPolicy（货币政策）, FiscalPolicy（财政政策）, RegulatoryPolicy（监管政策）,
Institution（机构）, FinancialConcept（金融概念）, InterestRate（利率）, ReserveRatio（准备金率）,
TaxRate（税率）, Quota（配额）, Market（市场）, Instrument（工具）,
Event（事件）, Indicator（指标）, Person（人物）, Document（文档）,
ActionType（措施大类）, Condition（适用条件）, Strategy（策略）, Region（地区）, CompanyType（企业类型）, Industry（行业）

【允许的关系类型】
issues（发布）: Institution → Policy
modifies（修订）: Policy → Policy
repeals（废止）: Policy → Policy
amends（修订替代）: Policy → Policy
affects（影响）: Policy → FinancialConcept/Market/InterestRate/ReserveRatio
sets（设定值）: Policy → Indicator/InterestRate/ReserveRatio
targets（针对）: Policy → Market/Institution
references（引用）: Policy → Policy
cites_as_basis（依据）: Policy → Policy
leads_to（导致）: Event → Event / ActionType → Strategy
mentions（提及）: Document → Entity
has_indicator（含指标）: Policy → Indicator
valid_during（有效期）: Policy → TimeInterval
similar_to（相似）: Policy → Policy
provides（提供）: Policy → ActionType
has_eligibility（适用条件）: Policy → Condition
subregion_of（子区域）: Region → Region

【Schema 约束】
- issues 关系的主语必须是 Institution，宾语必须是 Policy
- sets 关系必须附带具体数值和时间
- modifies/repeals/amends 关系的主语和宾语都必须是 Policy
- 每个实体必须指定类型，不得使用类型以外的自定义类型
- ActionType 仅限6大类：融资类、财政类、税收类、风险类、投资类、人才类
- Condition 的 category 仅限：region、company_type、industry

【关系归一化规则】
当文本中出现以下语义相近的关系词时，请使用归一化后的标准关系名：
- "鼓励""支持""扶持""推动" → 统一使用 provides
- "补贴""资助""奖补""拨款""专项资金" → 统一使用 provides
- "限制""约束""管控" → 使用 targets（不归一）
- "废止""取消""废除" → 使用 repeals（不归一）
- "修订""修改""调整""修正" → 使用 amends
注意：语义方向不同的词绝不合并。"限制"≠"支持"，"废止"≠"修订"。如果拿不准，保持原文关系名。

【时序信息抽取规则】
如文本中提到政策的生效/废止时间，请在 Policy 实体的 attributes 中标注：
- effective_date：生效日期（ISO 格式，如 "2025-01-01"）
- expiry_date：失效日期（ISO 格式，如 "2026-12-31"）
- status：默认 "active"；如果文本明确说"已废止"，标注 "repealed"
注意：
- "自发布之日起施行" → effective_date 填发布日期，status 填 "active"
- "有效期3年" → effective_date 填发布日期，expiry_date 填发布日期+3年
- 找不到明确时间 → 不填，留空
- 遇到"本文废止了 XXX""自本法施行之日起，XXX 同时废止"等表述 → 添加 repeals 关系
- 遇到"修订""修改"等表述且涉及具体条款变更 → 添加 amends 关系
"""

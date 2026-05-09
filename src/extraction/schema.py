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
}


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

    def validate(self) -> list[str]:
        """校验三元组是否符合 Schema 约束，返回问题列表"""
        issues = []

        # 校验关系类型
        try:
            RelationType(self.relation)
        except ValueError:
            issues.append(f"未知关系类型: {self.relation}")
            return issues

        # 校验主语/宾语类型约束
        if self.relation in RELATION_CONSTRAINTS:
            subj_types, obj_types = RELATION_CONSTRAINTS[self.relation]
            if subj_types and self.subject.entity_type not in subj_types:
                # 检查层级父类
                parent = ENTITY_HIERARCHY.get(self.subject.entity_type)
                if parent not in subj_types:
                    issues.append(
                        f"关系 {self.relation} 主语应为 {subj_types}，"
                        f"实际为 {self.subject.entity_type}"
                    )
            if obj_types and self.object_.entity_type not in obj_types:
                parent = ENTITY_HIERARCHY.get(self.object_.entity_type)
                if parent not in obj_types:
                    issues.append(
                        f"关系 {self.relation} 宾语应为 {obj_types}，"
                        f"实际为 {self.object_.entity_type}"
                    )

        return issues

    def to_dict(self) -> dict:
        """转为字典格式"""
        return {
            "subject": {"name": self.subject.name, "type": self.subject.entity_type},
            "relation": self.relation,
            "object": {"name": self.object_.name, "type": self.object_.entity_type},
            "confidence": self.confidence,
            "source_text": self.source_text,
            "source_chunk_id": self.source_chunk_id,
        }


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
- modifies/repeals 关系的主语和宾语都必须是 Policy
- 每个实体必须指定类型，不得使用类型以外的自定义类型
- ActionType 仅限6大类：融资类、财政类、税收类、风险类、投资类、人才类
- Condition 的 category 仅限：region、company_type、industry
"""

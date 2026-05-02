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
    LEADS_TO = "leads_to"           # 导致：Event → Event
    MENTIONS = "mentions"           # 提及：Document → Entity
    HAS_INDICATOR = "has_indicator" # 含指标：Policy → Indicator
    VALID_DURING = "valid_during"   # 有效期：Policy → TimeInterval
    SIMILAR_TO = "similar_to"       # 相似：Policy → Policy


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
    "leads_to":       (["Event"], ["Event"]),
    "mentions":       (["Document"], ["Policy", "Institution", "FinancialConcept"]),
    "has_indicator":  (["Policy"], ["Indicator"]),
    "valid_during":   (["Policy"], []),
    "similar_to":     (["Policy"], ["Policy"]),
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
        }


# ══════════════════════════════════════════
# Schema Prompt 注入文本
# ══════════════════════════════════════════

SCHEMA_PROMPT = """【允许的实体类型】
Policy（政策）, MonetaryPolicy（货币政策）, FiscalPolicy（财政政策）, RegulatoryPolicy（监管政策）,
Institution（机构）, FinancialConcept（金融概念）, InterestRate（利率）, ReserveRatio（准备金率）,
TaxRate（税率）, Quota（配额）, Market（市场）, Instrument（工具）,
Event（事件）, Indicator（指标）, Person（人物）, Document（文档）

【允许的关系类型】
issues（发布）: Institution → Policy
modifies（修订）: Policy → Policy
repeals（废止）: Policy → Policy
affects（影响）: Policy → FinancialConcept/Market/InterestRate/ReserveRatio
sets（设定值）: Policy → Indicator/InterestRate/ReserveRatio
targets（针对）: Policy → Market/Institution
references（引用）: Policy → Policy
cites_as_basis（依据）: Policy → Policy
leads_to（导致）: Event → Event
mentions（提及）: Document → Entity
has_indicator（含指标）: Policy → Indicator
valid_during（有效期）: Policy → TimeInterval
similar_to（相似）: Policy → Policy

【Schema 约束】
- issues 关系的主语必须是 Institution，宾语必须是 Policy
- sets 关系必须附带具体数值和时间
- modifies/repeals 关系的主语和宾语都必须是 Policy
- 每个实体必须指定类型，不得使用类型以外的自定义类型
"""

"""
预置条件定义表

将常见政策条件描述展开为可执行的 CondSub 原子条件。
这些定义在 KG 初始化时写入 Neo4j，也可通过 API 动态增删。

数据来源：
- 工信部联企业〔2011〕300号（中小企业划型标准）
- 国科发火〔2016〕32号（高新技术企业认定管理办法）
- 深圳市各政策文件中的常见条件
"""

from src.decision.cond_sub import CondDef, CondSub, CondOp

# ══════════════════════════════════════════
# 预置条件定义（14 个常见政策条件）
# ══════════════════════════════════════════

PRESET_COND_DEFS: list[CondDef] = [
    # ── 1. 中小微企业 ──
    CondDef(
        condition_text="中小微企业",
        category="company_type",
        aliases=["中小企业", "小微企业", "中小微", "中小型企业"],
        sub_conditions=[
            CondSub(field="is_sme", op=CondOp.EQ, value=True, is_hard=True,
                    description="企业为中小微企业"),
            # 备选：如果 is_sme 未填，用规模判断
            CondSub(field="annual_revenue", op=CondOp.LT, value=2000, is_hard=False,
                    description="年营收 < 2000万（中小微标准之一）",
                    source="工信部联企业〔2011〕300号"),
            CondSub(field="employees", op=CondOp.LT, value=300, is_hard=False,
                    description="员工 < 300人（中小微标准之一）",
                    source="工信部联企业〔2011〕300号"),
        ],
    ),

    # ── 2. 高新技术企业 ──
    CondDef(
        condition_text="高新技术企业",
        category="qualification",
        aliases=["高新企业", "国家高新技术企业", "高新"],
        sub_conditions=[
            CondSub(field="is_high_tech", op=CondOp.EQ, value=True, is_hard=True,
                    description="企业为高新技术企业",
                    source="国科发火〔2016〕32号"),
        ],
    ),

    # ── 3. 专精特新企业 ──
    CondDef(
        condition_text="专精特新企业",
        category="qualification",
        aliases=["专精特新", "专精特新中小企业", "专精特新小巨人"],
        sub_conditions=[
            CondSub(field="qualifications", op=CondOp.CONTAINS, value="专精特新", is_hard=True,
                    description="企业拥有专精特新资质"),
        ],
    ),

    # ── 4. 瞪羚企业 ──
    CondDef(
        condition_text="瞪羚企业",
        category="qualification",
        aliases=["瞪羚"],
        sub_conditions=[
            CondSub(field="qualifications", op=CondOp.CONTAINS, value="瞪羚企业", is_hard=True,
                    description="企业拥有瞪羚企业资质"),
        ],
    ),

    # ── 5. 战略性新兴产业 ──
    CondDef(
        condition_text="战略性新兴产业",
        category="industry",
        aliases=["新兴产业", "战略新兴产业", "战略性产业"],
        sub_conditions=[
            CondSub(
                field="industry", op=CondOp.IN,
                value=[
                    "人工智能", "AI算法", "AI应用", "AI硬件",
                    "物联网", "新能源", "新材料", "生物医药",
                    "集成电路", "高端装备", "航空航天", "智能制造",
                    "信息技术", "数字经济", "绿色低碳", "新能源汽车",
                    "节能环保", "新一代信息技术",
                ],
                is_hard=True,
                description="行业属于战略性新兴产业目录",
            ),
        ],
    ),

    # ── 6. 先进制造业 ──
    CondDef(
        condition_text="先进制造业",
        category="industry",
        aliases=["制造业", "高端制造", "智能制造"],
        sub_conditions=[
            CondSub(
                field="industry", op=CondOp.IN,
                value=["制造业", "智能制造", "高端装备", "集成电路", "新能源", "新材料"],
                is_hard=True,
                description="行业属于先进制造业",
            ),
        ],
    ),

    # ── 7. 深圳注册企业 ──
    CondDef(
        condition_text="深圳注册企业",
        category="region",
        aliases=["深圳市企业", "在深注册", "深圳企业", "深圳市注册"],
        sub_conditions=[
            CondSub(
                field="region", op=CondOp.IN,
                value=[
                    "深圳", "深圳市", "深圳南山", "深圳福田", "深圳宝安",
                    "深圳坪山", "深圳龙岗", "深圳龙华", "深圳光明", "深圳罗湖",
                    "深圳盐田", "深圳大鹏", "深圳深汕",
                    "南山区", "福田区", "宝安区", "坪山区",
                    "龙岗区", "龙华区", "光明区", "罗湖区",
                    "盐田区", "大鹏新区", "深汕特别合作区",
                ],
                is_hard=True,
                description="企业在深圳注册",
            ),
        ],
    ),

    # ── 8. 成立满N年 ──
    CondDef(
        condition_text="成立满2年",
        category="operation_years",
        aliases=["成立2年以上", "成立超过2年", "经营2年以上"],
        sub_conditions=[
            CondSub(field="established_date", op=CondOp.YEARS_SINCE, value=2, is_hard=True,
                    description="企业成立满2年"),
        ],
    ),

    CondDef(
        condition_text="成立满3年",
        category="operation_years",
        aliases=["成立3年以上", "成立超过3年", "经营3年以上"],
        sub_conditions=[
            CondSub(field="established_date", op=CondOp.YEARS_SINCE, value=3, is_hard=True,
                    description="企业成立满3年"),
        ],
    ),

    # ── 9. 年营收要求 ──
    CondDef(
        condition_text="年营收500万以上",
        category="revenue",
        aliases=["营收500万以上", "年营收不低于500万", "营业收入500万以上"],
        sub_conditions=[
            CondSub(field="annual_revenue", op=CondOp.GTE, value=500, is_hard=False,
                    description="年营收 ≥ 500万元"),
        ],
    ),

    CondDef(
        condition_text="年营收2000万以上",
        category="revenue",
        aliases=["营收2000万以上", "年营收不低于2000万"],
        sub_conditions=[
            CondSub(field="annual_revenue", op=CondOp.GTE, value=2000, is_hard=False,
                    description="年营收 ≥ 2000万元"),
        ],
    ),

    # ── 10. 员工人数要求 ──
    CondDef(
        condition_text="员工30人以上",
        category="employees",
        aliases=["从业人员30人以上", "员工不少于30人"],
        sub_conditions=[
            CondSub(field="employees", op=CondOp.GTE, value=30, is_hard=False,
                    description="员工 ≥ 30人"),
        ],
    ),

    # ── 11. 研发费用占比 ──
    CondDef(
        condition_text="研发费用占比3%以上",
        category="rd_ratio",
        aliases=["研发投入占比3%以上", "研发占比3%以上"],
        sub_conditions=[
            CondSub(field="rd_ratio", op=CondOp.GTE, value=3.0, is_hard=False,
                    description="研发费用占比 ≥ 3%"),
        ],
    ),

    # ── 12. 拥有知识产权 ──
    CondDef(
        condition_text="拥有知识产权",
        category="ip",
        aliases=["有知识产权", "持有专利", "拥有自主知识产权", "知识产权"],
        sub_conditions=[
            CondSub(field="patents", op=CondOp.GT, value=0, is_hard=False,
                    description="拥有1项以上专利/知识产权"),
        ],
    ),
]


def get_all_cond_defs() -> list[CondDef]:
    """获取全部预置条件定义"""
    return PRESET_COND_DEFS


def find_cond_def(condition_text: str) -> CondDef | None:
    """
    根据条件文本查找匹配的 CondDef

    优先精确匹配 condition_text，其次匹配 aliases
    """
    # 精确匹配
    for cd in PRESET_COND_DEFS:
        if cd.condition_text == condition_text:
            return cd

    # 别名匹配
    for cd in PRESET_COND_DEFS:
        if condition_text in cd.aliases:
            return cd

    # 模糊匹配：condition_text 包含定义名，或定义名包含 condition_text
    for cd in PRESET_COND_DEFS:
        if cd.condition_text in condition_text or condition_text in cd.condition_text:
            return cd

    return None


def _str_to_cond_op(op_str: str):
    """将字符串映射到 CondOp 枚举"""
    from src.decision.cond_sub import CondOp
    mapping = {
        "eq": CondOp.EQ, "in": CondOp.IN, "contains": CondOp.CONTAINS,
        "gte": CondOp.GTE, "lte": CondOp.LTE, "gt": CondOp.GT,
        "lt": CondOp.LT, "years_since": CondOp.YEARS_SINCE,
    }
    return mapping.get(op_str)


def expand_condition(condition_text: str, neo4j_store=None) -> list[CondSub]:
    """
    将条件文本展开为原子条件列表

    查找优先级（Phase 4 新增 CANONICAL_MAP）：
    0. CONDITION_CANONICAL_MAP — 直接映射，零 LLM 开销，覆盖 12/15 画像字段
    1. KG-first: Neo4j CondDef → CondSub
    2. Fallback: Python 硬编码 PRESET_COND_DEFS
    如果找不到匹配的 CondDef，返回空列表（EligibilityEngine 将标记为 unknown）
    """
    # 0. Phase 4: CONDITION_CANONICAL_MAP 直接映射
    from src.extraction.schema import CONDITION_CANONICAL_MAP
    canonical = CONDITION_CANONICAL_MAP.get(condition_text)
    if canonical:
        op = _str_to_cond_op(canonical["op"])
        if op is not None:
            return [CondSub(
                field=canonical["field"],
                op=op,
                value=canonical["value"],
                is_hard=True,
                description=f"映射表直接映射: {condition_text} → {canonical['field']}",
                source="canonical_map",
            )]

    # 1. KG-first: 从 Neo4j 查找
    if neo4j_store is not None:
        kg_result = _expand_from_kg(condition_text, neo4j_store)
        if kg_result:
            return kg_result

    # 2. Fallback: Python 硬编码
    cd = find_cond_def(condition_text)
    if cd:
        return cd.expand()
    return []


def _expand_from_kg(condition_text: str, neo4j_store) -> list[CondSub]:
    """从 Neo4j 查找 CondDef→CondSub 并转换为 CondSub 列表"""
    try:
        data = neo4j_store.find_cond_def(condition_text)
        if not data:
            return []

        subs = []
        for sub_data in data.get("sub_conditions", []):
            # 将 KG 中的 op 字符串转换回 CondOp 枚举
            op_str = sub_data.get("op", "")
            op = None
            for member in CondOp:
                if member.value == op_str:
                    op = member
                    break
            if op is None:
                continue

            # 处理 value 类型（KG 中 list 类型存为字符串需还原）
            value = sub_data.get("value")
            if isinstance(value, str) and value.startswith("["):
                try:
                    import json
                    value = json.loads(value.replace("'", '"'))
                except Exception:
                    pass

            subs.append(CondSub(
                field=sub_data.get("field", ""),
                op=op,
                value=value,
                is_hard=sub_data.get("is_hard", True),
                description=sub_data.get("description", ""),
                source=sub_data.get("source", ""),
            ))
        return subs
    except Exception as e:
        from loguru import logger
        logger.debug(f"KG 条件展开失败 (fallback 到硬编码): {condition_text} - {e}")
        return []

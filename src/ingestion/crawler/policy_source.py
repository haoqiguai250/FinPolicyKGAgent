"""
政策源配置模块（API 搜索模式）
通过深圳政策文件库 API 搜索政策，不再硬编码死链 URL

核心 API:
  GET https://zcwjk.xxgk.sz.gov.cn:9091/test/article/queryEs

层级映射:
  - national:     country="中华人民共和国"
  - provincial:   province="广东省"
  - municipal:    city="深圳市"
  - district:     area="XX区"
"""

from dataclasses import dataclass, field
from typing import Optional


# ── API 配置 ──

API_BASE_URL = "https://zcwjk.xxgk.sz.gov.cn:9091/test/article/queryEs"
API_PAGE_SIZE = 20  # 每页条数（API 最大 20）


@dataclass
class ApiSearchConfig:
    """API 搜索配置：一个搜索任务 = 一组关键词 + 层级筛选"""
    name: str                                       # 搜索任务名称
    level: str                                      # 层级: national / provincial / municipal / district
    search_keywords: list[str] = field(default_factory=list)  # 搜索关键词列表
    country: str = ""                               # 国家筛选
    province: str = ""                              # 省份筛选
    city: str = ""                                  # 城市筛选
    area: str = ""                                  # 区县筛选
    policy_theme: str = ""                          # 政策主题筛选
    policy_cat: str = ""                            # 政策类型筛选
    enterprise_scale_label: str = ""                # 企业规模筛选（如 "中小微企业"）
    enabled: bool = True                            # 是否启用


# ── 四层关键词体系 ──

KEYWORDS = {
    # 层1：低空核心词（一搜就中）
    "core": [
        "低空经济", "低空产业", "低空飞行",
        "无人机", "无人驾驶航空器", "无人机配送", "无人机物流",
        "eVTOL", "电动垂直起降", "飞行汽车",
        "城市空中交通", "UAM", "空中交通管理",
        "通航", "通用航空", "低空旅游",
        "低空基础设施", "起降场", "低空通信", "低空导航",
        "低空空域", "空域管理", "空域划设",
        "低空制造", "低空服务",
        "低空经济示范", "低空经济产业园",
    ],

    # 层2：产业配套词（低空企业相关）
    "industry": [
        "低空人才", "低空基金", "低空金融",
        "无人机反制", "无人机管控", "无人机保险",
        "低空数据", "低空遥感",
        "低空标准", "低空认证",
    ],

    # 层3：通用扶持词（低空企业可适用）
    "support": [
        "瞪羚企业", "独角兽企业", "专精特新", "小巨人",
        "高新技术企业", "科技型中小企业",
        "研发投入补助", "研发费用资助", "研发资助",
        "技术改造", "智能制造", "数字化转型",
        "贷款贴息", "融资担保", "信贷支持", "风险补偿",
        "人才引进", "住房补贴", "创业资助", "人才房",
        "产业基金", "股权投资", "专项资金", "财政补贴",
        "首台套", "首版次", "重大技术装备",
        "产业扶持", "稳增长", "高质量发展",
    ],

    # 层4：部门关联词（搜索限定）
    "department": [
        "民航局", "CAAC",
        "交通运输部",
        "空管委", "空域管理",
        "深圳交通局", "低空经济处",
        "龙华低空", "南山低空", "宝安低空",
    ],

    # 层5：科技/IT词（与企业画像匹配）
    "tech": [
        "人工智能", "AI", "大模型", "智能制造",
        "软件产业", "软件和信息技术", "IT",
        "数字经济", "数字化转型", "工业互联网",
        "半导体", "集成电路", "芯片",
        "5G", "6G", "物联网", "大数据", "云计算",
        "区块链", "数据安全", "网络安全",
        "科技企业", "科技创新", "研发投入",
    ],

    # 层6：中小企业词（中小企业方向专用）
    "sme": [
        # 核心词
        "中小企业", "小微企业", "专精特新", "民营企业", "微型企业",
        # 扩展词
        "初创企业", "科技型中小企业", "创新型中小企业", "企业培育", "企业纾困",
        # 扶持方向
        "中小企业融资", "中小企业补贴", "中小企业扶持",
        "民营企业发展", "民营经济", "小巨人",
    ],

    # 层7：企业补助核心词（企业补助方向专用）
    "subsidy_core": [
        "企业补助", "企业补贴", "财政补贴", "财政资助",
        "专项资金", "资助办法", "扶持措施", "若干措施",
        "奖励办法", "补贴政策", "资助政策", "补助政策",
        "扶持资金", "发展资金", "产业资金",
    ],

    # 层8：企业补助细分词（按扶持类型细分）
    "subsidy_detail": [
        # 研发/创新
        "研发补助", "研发资助", "研发费用", "创新资助", "技术改造",
        "科技创新", "科技成果转化", "知识产权资助",
        # 融资/金融
        "贷款贴息", "融资担保", "融资补贴", "信贷支持", "风险补偿",
        # 人才/住房
        "人才补贴", "人才住房", "住房补贴", "人才引进", "新引进人才",
        # 产业/空间
        "厂房补贴", "租金补贴", "空间扶持", "产业用房",
        # 数字化/绿色
        "数字化转型", "绿色低碳", "节能减排", "碳达峰",
        # 高新技术
        "高新技术企业", "专精特新", "小巨人", "瞪羚企业",
    ],
}


# ── API 搜索任务列表 ──
# 每个任务对应一组搜索关键词 + 层级筛选
# API 会返回匹配的政策条目（标题、URL、发布时间、部门等）

API_SEARCH_TASKS: list[ApiSearchConfig] = [
    # ━━━ 国家级 ━━━
    # API 的 country/province 筛选对深圳政策库意义不大（全是深圳收录的）
    # 纯靠关键词搜索即可，层级标记仅用于结果分类
    ApiSearchConfig(
        name="国家级-低空核心",
        level="national",
        search_keywords=["低空经济", "无人机", "eVTOL", "通用航空", "无人驾驶航空器"],
    ),

    # ━━━ 广东省 ━━━
    ApiSearchConfig(
        name="广东省-低空核心",
        level="provincial",
        search_keywords=["低空经济", "无人机", "eVTOL", "通用航空"],
    ),

    # ━━━ 深圳市级 ━━━
    # 注意: city="深圳市" 会导致返回 0 条（深圳政策库默认就是深圳市的）
    # 市级政策不传 city 参数，通过关键词搜索即可
    ApiSearchConfig(
        name="深圳市-低空核心",
        level="municipal",
        search_keywords=["低空经济", "低空产业", "低空飞行", "无人机"],
    ),
    ApiSearchConfig(
        name="深圳市-低空配套",
        level="municipal",
        search_keywords=["低空人才", "低空基金", "低空基础设施", "起降场"],
    ),

    # ━━━ 区级 ━━━
    # area 参数可以精确筛选区级政策，city 不需要传
    ApiSearchConfig(
        name="龙华区-低空",
        level="district",
        search_keywords=["低空经济", "无人机"],
        area="龙华区",
    ),
    ApiSearchConfig(
        name="南山区-低空",
        level="district",
        search_keywords=["低空经济", "无人机"],
        area="南山区",
    ),
    ApiSearchConfig(
        name="宝安区-低空",
        level="district",
        search_keywords=["低空经济", "无人机"],
        area="宝安区",
    ),
    ApiSearchConfig(
        name="福田区-低空",
        level="district",
        search_keywords=["低空经济", "无人机"],
        area="福田区",
    ),
    ApiSearchConfig(
        name="龙岗区-低空",
        level="district",
        search_keywords=["低空经济", "无人机"],
        area="龙岗区",
    ),
    ApiSearchConfig(
        name="光明区-低空",
        level="district",
        search_keywords=["低空经济", "无人机"],
        area="光明区",
    ),
    ApiSearchConfig(
        name="坪山区-低空",
        level="district",
        search_keywords=["低空经济", "无人机"],
        area="坪山区",
    ),

    # ━━━ 科技/IT 方向 ━━━
    ApiSearchConfig(
        name="国家级-科技IT",
        level="national",
        search_keywords=["人工智能", "数字经济", "集成电路", "软件产业", "数字化转型"],
    ),
    ApiSearchConfig(
        name="广东省-科技IT",
        level="provincial",
        search_keywords=["人工智能", "数字经济", "集成电路", "数字化转型", "科技创新"],
    ),
    ApiSearchConfig(
        name="深圳市-科技IT",
        level="municipal",
        search_keywords=["人工智能", "数字经济", "集成电路", "软件产业", "数字化转型"],
    ),
    ApiSearchConfig(
        name="龙华区-科技IT",
        level="district",
        search_keywords=["人工智能", "数字经济", "数字化转型"],
        area="龙华区",
    ),
    ApiSearchConfig(
        name="南山区-科技IT",
        level="district",
        search_keywords=["人工智能", "数字经济", "数字化转型"],
        area="南山区",
    ),
    ApiSearchConfig(
        name="宝安区-科技IT",
        level="district",
        search_keywords=["人工智能", "数字经济", "数字化转型"],
        area="宝安区",
    ),
    ApiSearchConfig(
        name="坪山区-科技IT",
        level="district",
        search_keywords=["人工智能", "数字经济", "数字化转型"],
        area="坪山区",
    ),

    # ━━━ 中小企业方向 ━━━
    ApiSearchConfig(
        name="深圳市-中小企业核心",
        level="municipal",
        search_keywords=["中小企业", "小微企业", "专精特新", "民营企业"],
        enterprise_scale_label="中小微企业",
    ),
    ApiSearchConfig(
        name="深圳市-中小企业扶持",
        level="municipal",
        search_keywords=["中小企业融资", "中小企业补贴", "企业纾困", "民营经济"],
        enterprise_scale_label="中小微企业",
    ),
    ApiSearchConfig(
        name="广东省-中小企业",
        level="provincial",
        search_keywords=["中小企业", "小微企业", "民营企业", "专精特新"],
    ),
    ApiSearchConfig(
        name="国家级-中小企业",
        level="national",
        search_keywords=["中小企业", "小微企业", "民营企业", "专精特新"],
    ),
    ApiSearchConfig(
        name="龙华区-中小企业",
        level="district",
        search_keywords=["中小企业", "小微企业"],
        area="龙华区",
    ),
    ApiSearchConfig(
        name="南山区-中小企业",
        level="district",
        search_keywords=["中小企业", "专精特新"],
        area="南山区",
    ),
    ApiSearchConfig(
        name="宝安区-中小企业",
        level="district",
        search_keywords=["中小企业", "小微企业", "民营企业"],
        area="宝安区",
    ),
    ApiSearchConfig(
        name="坪山区-中小企业",
        level="district",
        search_keywords=["中小企业", "企业培育"],
        area="坪山区",
    ),

    # ━━━ 企业补助方向 ━━━
    # 聚焦深圳市及各区对企业补助/补贴/资助的政策

    # 深圳市级 — 补助核心
    ApiSearchConfig(
        name="深圳市-企业补助核心",
        level="municipal",
        search_keywords=["企业补助", "企业补贴", "财政补贴", "专项资金", "资助办法"],
    ),
    # 深圳市级 — 研发创新补助
    ApiSearchConfig(
        name="深圳市-研发创新补助",
        level="municipal",
        search_keywords=["研发补助", "研发资助", "研发费用", "创新资助", "科技成果转化"],
    ),
    # 深圳市级 — 融资贷款补贴
    ApiSearchConfig(
        name="深圳市-融资贷款补贴",
        level="municipal",
        search_keywords=["贷款贴息", "融资担保", "融资补贴", "信贷支持", "风险补偿"],
    ),
    # 深圳市级 — 人才补贴
    ApiSearchConfig(
        name="深圳市-人才补贴",
        level="municipal",
        search_keywords=["人才补贴", "人才住房", "住房补贴", "人才引进", "新引进人才"],
    ),
    # 深圳市级 — 数字化/绿色补贴
    ApiSearchConfig(
        name="深圳市-数字化绿色补贴",
        level="municipal",
        search_keywords=["数字化转型", "绿色低碳", "节能减排", "技术改造", "智能制造"],
    ),
    # 深圳市级 — 扶持措施/若干措施
    ApiSearchConfig(
        name="深圳市-扶持措施",
        level="municipal",
        search_keywords=["扶持措施", "若干措施", "奖励办法", "扶持资金", "发展资金"],
    ),

    # 各区 — 企业补助
    ApiSearchConfig(
        name="福田区-企业补助",
        level="district",
        search_keywords=["企业补助", "企业补贴", "专项资金", "资助办法"],
        area="福田区",
    ),
    ApiSearchConfig(
        name="南山区-企业补助",
        level="district",
        search_keywords=["企业补助", "企业补贴", "专项资金", "研发资助"],
        area="南山区",
    ),
    ApiSearchConfig(
        name="宝安区-企业补助",
        level="district",
        search_keywords=["企业补助", "企业补贴", "专项资金", "扶持措施"],
        area="宝安区",
    ),
    ApiSearchConfig(
        name="龙岗区-企业补助",
        level="district",
        search_keywords=["企业补助", "企业补贴", "专项资金", "若干措施"],
        area="龙岗区",
    ),
    ApiSearchConfig(
        name="龙华区-企业补助",
        level="district",
        search_keywords=["企业补助", "企业补贴", "专项资金", "资助办法"],
        area="龙华区",
    ),
    ApiSearchConfig(
        name="坪山区-企业补助",
        level="district",
        search_keywords=["企业补助", "企业补贴", "专项资金", "若干措施", "扶持措施"],
        area="坪山区",
    ),
    ApiSearchConfig(
        name="光明区-企业补助",
        level="district",
        search_keywords=["企业补助", "企业补贴", "专项资金", "资助办法"],
        area="光明区",
    ),
    ApiSearchConfig(
        name="罗湖区-企业补助",
        level="district",
        search_keywords=["企业补助", "企业补贴", "专项资金", "扶持措施"],
        area="罗湖区",
    ),
    ApiSearchConfig(
        name="盐田区-企业补助",
        level="district",
        search_keywords=["企业补助", "企业补贴", "专项资金"],
        area="盐田区",
    ),
    ApiSearchConfig(
        name="大鹏新区-企业补助",
        level="district",
        search_keywords=["企业补助", "企业补贴", "专项资金"],
        area="大鹏新区",
    ),

    # ━━━ 广东省企业补助 ━━━
    ApiSearchConfig(
        name="广东省-企业补助核心",
        level="provincial",
        search_keywords=["企业补助", "企业补贴", "财政补贴", "专项资金", "资助办法"],
    ),
    ApiSearchConfig(
        name="广东省-研发创新",
        level="provincial",
        search_keywords=["研发补助", "研发资助", "创新资助", "科技成果转化", "技术改造"],
    ),
    ApiSearchConfig(
        name="广东省-融资贷款",
        level="provincial",
        search_keywords=["贷款贴息", "融资担保", "融资补贴", "信贷支持", "风险补偿"],
    ),
    ApiSearchConfig(
        name="广东省-人才住房",
        level="provincial",
        search_keywords=["人才补贴", "人才住房", "住房补贴", "人才引进"],
    ),
    ApiSearchConfig(
        name="广东省-数字化绿色",
        level="provincial",
        search_keywords=["数字化转型", "绿色低碳", "节能减排", "智能制造"],
    ),
    ApiSearchConfig(
        name="广东省-扶持措施",
        level="provincial",
        search_keywords=["扶持措施", "若干措施", "奖励办法", "扶持资金", "发展资金", "产业资金"],
    ),

    # ━━━ 国家级企业补助 ━━━
    ApiSearchConfig(
        name="国家级-企业补助",
        level="national",
        search_keywords=["企业补助", "企业补贴", "财政补贴", "专项资金", "资助办法"],
    ),
    ApiSearchConfig(
        name="国家级-研发融资",
        level="national",
        search_keywords=["研发补助", "贷款贴息", "融资担保", "风险补偿", "信贷支持"],
    ),
    ApiSearchConfig(
        name="国家级-产业扶持",
        level="national",
        search_keywords=["扶持措施", "若干措施", "奖励办法", "技术改造", "数字化转型"],
    ),

    # 广东省 — 企业补助
    ApiSearchConfig(
        name="广东省-企业补助",
        level="provincial",
        search_keywords=["企业补助", "企业补贴", "专项资金", "资助办法", "扶持措施"],
    ),
]


# ── 辅助函数 ──

def get_search_tasks_by_level(level: str) -> list[ApiSearchConfig]:
    """按层级筛选搜索任务"""
    return [t for t in API_SEARCH_TASKS if t.level == level and t.enabled]


def get_enabled_search_tasks() -> list[ApiSearchConfig]:
    """获取所有启用的搜索任务"""
    return [t for t in API_SEARCH_TASKS if t.enabled]


def get_keywords(layers: list[str] | None = None) -> list[str]:
    """
    获取关键词列表

    Args:
        layers: 要包含的关键词层，默认 ["core", "industry"]
                可选: core / industry / support / department

    Returns:
        去重后的关键词列表
    """
    if layers is None:
        layers = ["core", "industry"]

    result = []
    for layer in layers:
        result.extend(KEYWORDS.get(layer, []))
    return list(set(result))


# ── 兼容旧代码的别名 ──
# PolicySource 保留为 ApiSearchConfig 的别名，方便外部引用
PolicySource = ApiSearchConfig
POLICY_SOURCES = API_SEARCH_TASKS


def get_sources_by_level(level: str) -> list[PolicySource]:
    """按层级筛选政策源（兼容旧接口）"""
    return get_search_tasks_by_level(level)


def get_enabled_sources() -> list[PolicySource]:
    """获取所有启用的政策源（兼容旧接口）"""
    return get_enabled_search_tasks()

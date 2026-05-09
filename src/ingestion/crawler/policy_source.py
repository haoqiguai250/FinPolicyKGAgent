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

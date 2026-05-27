"""
API 数据模型 — ApplicationOpportunity 及相关类型

Phase 2 模块 C: 企业申报工作台的核心业务对象
"""

from datetime import datetime
from pydantic import BaseModel, Field


class EligibilityCheckBrief(BaseModel):
    """条件核验简要信息"""
    condition_text: str
    status: str  # pass / fail / unknown
    is_hard: bool = True
    reason: str = ""


class ApplicationOpportunity(BaseModel):
    """
    申报机会 — 企业与政策之间的业务对象

    这是 Phase 2 的核心实体，所有推送、工作台、通知、任务、状态流转
    都围绕 ApplicationOpportunity 展开
    """
    # ── 标识 ──
    opportunity_id: str = Field(default="", description="申报机会ID（自动生成）")
    policy_name: str
    policy_id: str = ""
    enterprise_id: str = ""

    # ── 核验状态 ──
    is_eligible: bool = False
    eligibility_checks: list[EligibilityCheckBrief] = []
    hard_pass_count: int = 0
    hard_fail_count: int = 0
    soft_pass_count: int = 0
    unknown_count: int = 0

    # ── 申报信息（从 KG 读取） ──
    required_materials: list[str] = []
    application_steps: list[str] = []
    deadline: str = ""
    platform_url: str = ""
    platform_name: str = ""
    source_department: str = ""
    estimated_amount: str = ""

    # ── LLM 生成 ──
    match_explanation: str = ""
    suggestions: str = ""

    # ── 运营状态 ──
    status: str = "discovered"  # discovered / applying / submitted / approved / rejected
    created_at: str = Field(default="", description="发现时间")

    # ── 截止提醒 ──
    days_until_deadline: int | None = None
    deadline_urgency: str | None = None  # high / medium / low

    # ── 政策有效期 ──
    effective_date: str = ""
    expiry_date: str = ""
    policy_status: str = ""  # active / repealed / expiring_soon


class OpportunitiesResponse(BaseModel):
    """申报机会列表响应"""
    total: int
    eligible_count: int
    ineligible_count: int
    missing_fields: list[str] = []
    opportunities: list[ApplicationOpportunity]


class MaterialItem(BaseModel):
    """材料清单项"""
    material_id: str = ""
    opportunity_id: str = ""
    material_name: str
    status: str = "preparing"  # preparing / ready / submitted / waived
    notes: str = ""
    source: str = "kg"  # kg / llm / manual
    created_at: str = ""
    updated_at: str = ""


class MaterialsProgress(BaseModel):
    """材料完成度"""
    total: int = 0
    ready_count: int = 0
    progress_pct: float = 0.0

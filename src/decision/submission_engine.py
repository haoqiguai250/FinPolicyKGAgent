"""
自动提交引擎

系统准备好所有材料和文件，人工确认后提交。
采用策略模式，未来可扩展 API/浏览器自动化。
"""

import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from loguru import logger


class SubmissionStrategy(ABC):
    """提交策略抽象基类"""

    @abstractmethod
    def prepare(self, opportunity: dict, materials: list[dict], documents: list[dict]) -> dict:
        """准备提交"""
        ...

    @abstractmethod
    def execute(self, package: dict, confirmed_by: str = "") -> dict:
        """执行提交"""
        ...


class ManualSubmissionStrategy(SubmissionStrategy):
    """人工确认提交策略"""

    def prepare(self, opportunity: dict, materials: list[dict], documents: list[dict]) -> dict:
        """准备提交包：冻结快照"""
        return {
            "package_id": str(uuid.uuid4()),
            "opportunity_id": opportunity["opportunity_id"],
            "status": "ready",
            "materials_checklist_json": json.dumps(materials, ensure_ascii=False),
            "documents_json": json.dumps(documents, ensure_ascii=False),
            "profile_snapshot_json": "{}",
            "policy_snapshot_json": json.dumps({
                "policy_name": opportunity.get("policy_name", ""),
                "platform_name": opportunity.get("platform_name", ""),
                "platform_url": opportunity.get("platform_url", ""),
                "deadline": opportunity.get("deadline", ""),
                "estimated_amount": opportunity.get("estimated_amount", ""),
                "source_department": opportunity.get("source_department", ""),
                "application_steps": json.loads(opportunity.get("application_steps_json", "[]"))
                    if isinstance(opportunity.get("application_steps_json"), str)
                    else opportunity.get("application_steps_json", []),
            }, ensure_ascii=False),
            "submission_strategy": "manual",
        }

    def execute(self, package: dict, confirmed_by: str = "") -> dict:
        """人工确认提交"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {
            "status": "submitted",
            "confirmed_by": confirmed_by or "manual",
            "confirmed_at": now,
            "submitted_at": now,
        }


class SubmissionEngine:
    """申报提交引擎"""

    def __init__(self, db, strategy: Optional[SubmissionStrategy] = None):
        self.db = db
        self.strategy = strategy or ManualSubmissionStrategy()

    def prepare_submission(self, opportunity_id: str) -> dict:
        """
        准备申报包

        校验:
        - opportunity 状态必须是 applying
        - 所有材料状态必须是 ready 或 waived
        """
        opp = self.db.get_opportunity(opportunity_id)
        if not opp:
            raise ValueError(f"申报机会不存在: {opportunity_id}")

        # 状态校验
        if opp["status"] != "applying":
            raise ValueError(f"当前状态 '{opp['status']}' 不可准备申报，需要 'applying' 状态")

        # 材料校验
        materials = self.db.list_materials(opportunity_id)
        not_ready = [
            m for m in materials
            if m["status"] not in ("ready", "submitted", "waived")
        ]
        if not_ready:
            names = ", ".join(m["material_name"] for m in not_ready)
            raise ValueError(f"以下材料尚未就绪: {names}")

        # 获取已生成文档
        documents = self.db.list_generated_documents(opportunity_id)

        # 构建申报包
        package_data = self.strategy.prepare(opp, materials, documents)

        # 获取企业画像快照
        enterprise_id = opp.get("enterprise_id", "")
        if enterprise_id:
            profile = self.db.get_enterprise_profile(enterprise_id)
            package_data["profile_snapshot_json"] = json.dumps(profile, ensure_ascii=False)

        # 写入 DB
        saved = self.db.upsert_submission_package(package_data)
        logger.info(f"申报包已准备: {opportunity_id} ({len(materials)} 条材料, {len(documents)} 个文档)")

        return saved

    def execute_submission(
        self,
        opportunity_id: str,
        confirmed_by: str = "",
    ) -> dict:
        """
        执行提交（人工确认）

        流程:
        1. 校验申报包存在且状态为 ready
        2. 调用策略执行提交
        3. 更新 opportunity 状态为 submitted
        4. 更新申报包状态
        """
        package = self.db.get_submission_package(opportunity_id)
        if not package:
            raise ValueError(f"申报包不存在，请先准备申报包")

        if package["status"] != "ready":
            raise ValueError(f"申报包状态 '{package['status']}' 不可提交，需要 'ready' 状态")

        # 执行提交
        result = self.strategy.execute(package, confirmed_by=confirmed_by)

        # 更新申报包
        package.update(result)
        self.db.upsert_submission_package(package)

        # 更新 opportunity 状态
        self.db.update_opportunity_status(
            opportunity_id=opportunity_id,
            new_status="submitted",
            event_type="submission",
            note=f"通过 {package.get('submission_strategy', 'manual')} 方式提交"
                 + (f"，确认人: {confirmed_by}" if confirmed_by else ""),
        )

        # 更新材料状态
        materials = self.db.list_materials(opportunity_id)
        for mat in materials:
            if mat["status"] == "ready":
                self.db.update_material(mat["material_id"], status="submitted")

        logger.info(f"申报已提交: {opportunity_id} (策略={package.get('submission_strategy')})")

        return {
            "opportunity_id": opportunity_id,
            "status": "submitted",
            "package_id": package.get("package_id", ""),
            "submitted_at": result.get("submitted_at", ""),
            "platform_url": json.loads(package.get("policy_snapshot_json", "{}")).get("platform_url", "")
                if isinstance(package.get("policy_snapshot_json"), str) else "",
        }

    def get_package(self, opportunity_id: str) -> Optional[dict]:
        """获取申报包"""
        return self.db.get_submission_package(opportunity_id)

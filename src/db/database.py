"""
SQLite 数据库管理 — 连接 + 建表 + 迁移

Phase 3 模块 E: 申报运营持久层

表结构:
- enterprises: 企业注册 + 画像快照
- opportunities: 申报机会（持久化 + 状态机）
- opportunity_events: 操作事件日志（事件溯源）
- material_checklist: 申报材料逐项管理
"""

import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from loguru import logger


class Database:
    """SQLite 数据库管理器"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()
        logger.info(f"SQLite 数据库初始化完成: {db_path}")

    @contextmanager
    def get_conn(self):
        """获取数据库连接（上下文管理器，自动 commit/rollback）"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_tables(self):
        """建表（幂等，重复执行不报错）"""
        with self.get_conn() as conn:
            # ── enterprises: 企业注册 + 画像快照 ──
            conn.execute("""CREATE TABLE IF NOT EXISTS enterprises (
                enterprise_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                profile_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )""")

            # ── opportunities: 申报机会（持久化 + 状态机） ──
            conn.execute("""CREATE TABLE IF NOT EXISTS opportunities (
                opportunity_id TEXT PRIMARY KEY,
                enterprise_id TEXT NOT NULL,
                policy_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'discovered'
                    CHECK(status IN ('discovered', 'applying', 'submitted', 'approved', 'rejected')),
                is_eligible INTEGER NOT NULL DEFAULT 0,
                eligibility_checks_json TEXT NOT NULL DEFAULT '[]',
                hard_pass_count INTEGER NOT NULL DEFAULT 0,
                hard_fail_count INTEGER NOT NULL DEFAULT 0,
                soft_pass_count INTEGER NOT NULL DEFAULT 0,
                unknown_count INTEGER NOT NULL DEFAULT 0,
                deadline TEXT NOT NULL DEFAULT '',
                deadline_urgency TEXT DEFAULT '',
                days_until_deadline INTEGER,
                estimated_amount TEXT DEFAULT '',
                platform_name TEXT DEFAULT '',
                platform_url TEXT DEFAULT '',
                source_department TEXT DEFAULT '',
                match_explanation TEXT DEFAULT '',
                suggestions TEXT DEFAULT '',
                required_materials_json TEXT NOT NULL DEFAULT '[]',
                application_steps_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (enterprise_id) REFERENCES enterprises(enterprise_id),
                UNIQUE(enterprise_id, policy_name)
            )""")

            # ── opportunity_events: 操作事件日志（事件溯源） ──
            conn.execute("""CREATE TABLE IF NOT EXISTS opportunity_events (
                event_id TEXT PRIMARY KEY,
                opportunity_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                old_status TEXT DEFAULT '',
                new_status TEXT DEFAULT '',
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (opportunity_id) REFERENCES opportunities(opportunity_id)
            )""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_events_opportunity
                ON opportunity_events(opportunity_id)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_events_created
                ON opportunity_events(created_at)""")

            # ── material_checklist: 申报材料逐项管理 ──
            conn.execute("""CREATE TABLE IF NOT EXISTS material_checklist (
                material_id TEXT PRIMARY KEY,
                opportunity_id TEXT NOT NULL,
                material_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'preparing'
                    CHECK(status IN ('preparing', 'ready', 'submitted', 'waived')),
                notes TEXT DEFAULT '',
                source TEXT NOT NULL DEFAULT 'kg'
                    CHECK(source IN ('kg', 'llm', 'manual')),
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (opportunity_id) REFERENCES opportunities(opportunity_id)
            )""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_materials_opportunity
                ON material_checklist(opportunity_id)""")

            # ── generated_documents: 生成的申报文档 ──
            conn.execute("""CREATE TABLE IF NOT EXISTS generated_documents (
                doc_id TEXT PRIMARY KEY,
                opportunity_id TEXT NOT NULL,
                material_id TEXT DEFAULT '',
                doc_name TEXT NOT NULL,
                doc_type TEXT NOT NULL DEFAULT 'docx'
                    CHECK(doc_type IN ('docx', 'pdf')),
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'generated'
                    CHECK(status IN ('generating', 'generated', 'error')),
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (opportunity_id) REFERENCES opportunities(opportunity_id)
            )""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_documents_opportunity
                ON generated_documents(opportunity_id)""")

            # ── submission_packages: 申报包（冻结快照） ──
            conn.execute("""CREATE TABLE IF NOT EXISTS submission_packages (
                package_id TEXT PRIMARY KEY,
                opportunity_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'preparing'
                    CHECK(status IN ('preparing', 'ready', 'submitted', 'error')),
                materials_checklist_json TEXT NOT NULL DEFAULT '[]',
                documents_json TEXT NOT NULL DEFAULT '[]',
                profile_snapshot_json TEXT NOT NULL DEFAULT '{}',
                policy_snapshot_json TEXT NOT NULL DEFAULT '{}',
                submission_strategy TEXT NOT NULL DEFAULT 'manual'
                    CHECK(submission_strategy IN ('manual', 'api', 'browser')),
                confirmed_by TEXT DEFAULT '',
                confirmed_at TEXT DEFAULT '',
                submitted_at TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (opportunity_id) REFERENCES opportunities(opportunity_id)
            )""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_packages_opportunity
                ON submission_packages(opportunity_id)""")

            # ── 索引 ──
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_opportunities_enterprise
                ON opportunities(enterprise_id)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_opportunities_status
                ON opportunities(status)""")

    # ══════════════════════════════════════════
    # Enterprise CRUD
    # ══════════════════════════════════════════

    def create_enterprise(self, enterprise_id: str, name: str, profile_json: str = "{}") -> dict:
        """创建企业，返回完整行"""
        with self.get_conn() as conn:
            conn.execute(
                "INSERT INTO enterprises (enterprise_id, name, profile_json) VALUES (?, ?, ?)",
                (enterprise_id, name, profile_json),
            )
            row = conn.execute(
                "SELECT * FROM enterprises WHERE enterprise_id = ?",
                (enterprise_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_enterprise(self, enterprise_id: str) -> Optional[dict]:
        """获取企业信息"""
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM enterprises WHERE enterprise_id = ?",
                (enterprise_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_enterprises(self) -> list[dict]:
        """企业列表"""
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM enterprises ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def update_enterprise_profile(self, enterprise_id: str, profile_json: str) -> Optional[dict]:
        """更新企业画像"""
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE enterprises SET profile_json = ?, updated_at = datetime('now', 'localtime') WHERE enterprise_id = ?",
                (profile_json, enterprise_id),
            )
            row = conn.execute(
                "SELECT * FROM enterprises WHERE enterprise_id = ?",
                (enterprise_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_enterprise_profile(self, enterprise_id: str) -> dict:
        """获取企业画像（解析 JSON）"""
        ent = self.get_enterprise(enterprise_id)
        if not ent:
            return {}
        try:
            return json.loads(ent["profile_json"])
        except (json.JSONDecodeError, TypeError):
            return {}

    # ══════════════════════════════════════════
    # Opportunity CRUD
    # ══════════════════════════════════════════

    def upsert_opportunity(self, opp: dict) -> dict:
        """
        创建或更新 Opportunity（upsert 逻辑）

        核心规则：
        - 新记录 → 直接 INSERT
        - 已存在 → 更新核验结果字段，但不覆盖 status（状态只能往前推进）
        """
        opp_id = opp["opportunity_id"]
        with self.get_conn() as conn:
            existing = conn.execute(
                "SELECT status FROM opportunities WHERE opportunity_id = ?",
                (opp_id,),
            ).fetchone()

            if existing:
                # 已存在：更新核验结果，不覆盖 status
                conn.execute("""UPDATE opportunities SET
                    is_eligible = ?,
                    eligibility_checks_json = ?,
                    hard_pass_count = ?,
                    hard_fail_count = ?,
                    soft_pass_count = ?,
                    unknown_count = ?,
                    deadline = ?,
                    deadline_urgency = ?,
                    days_until_deadline = ?,
                    estimated_amount = ?,
                    platform_name = ?,
                    platform_url = ?,
                    source_department = ?,
                    match_explanation = ?,
                    suggestions = ?,
                    required_materials_json = ?,
                    application_steps_json = ?,
                    updated_at = datetime('now', 'localtime')
                WHERE opportunity_id = ?""", (
                    opp["is_eligible"],
                    opp.get("eligibility_checks_json", "[]"),
                    opp.get("hard_pass_count", 0),
                    opp.get("hard_fail_count", 0),
                    opp.get("soft_pass_count", 0),
                    opp.get("unknown_count", 0),
                    opp.get("deadline", ""),
                    opp.get("deadline_urgency", ""),
                    opp.get("days_until_deadline"),
                    opp.get("estimated_amount", ""),
                    opp.get("platform_name", ""),
                    opp.get("platform_url", ""),
                    opp.get("source_department", ""),
                    opp.get("match_explanation", ""),
                    opp.get("suggestions", ""),
                    opp.get("required_materials_json", "[]"),
                    opp.get("application_steps_json", "[]"),
                    opp_id,
                ))
            else:
                # 新记录
                conn.execute("""INSERT INTO opportunities (
                    opportunity_id, enterprise_id, policy_name, status,
                    is_eligible, eligibility_checks_json,
                    hard_pass_count, hard_fail_count, soft_pass_count, unknown_count,
                    deadline, deadline_urgency, days_until_deadline,
                    estimated_amount, platform_name, platform_url, source_department,
                    match_explanation, suggestions,
                    required_materials_json, application_steps_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                    opp_id,
                    opp["enterprise_id"],
                    opp["policy_name"],
                    opp.get("status", "discovered"),
                    opp["is_eligible"],
                    opp.get("eligibility_checks_json", "[]"),
                    opp.get("hard_pass_count", 0),
                    opp.get("hard_fail_count", 0),
                    opp.get("soft_pass_count", 0),
                    opp.get("unknown_count", 0),
                    opp.get("deadline", ""),
                    opp.get("deadline_urgency", ""),
                    opp.get("days_until_deadline"),
                    opp.get("estimated_amount", ""),
                    opp.get("platform_name", ""),
                    opp.get("platform_url", ""),
                    opp.get("source_department", ""),
                    opp.get("match_explanation", ""),
                    opp.get("suggestions", ""),
                    opp.get("required_materials_json", "[]"),
                    opp.get("application_steps_json", "[]"),
                ))

            row = conn.execute(
                "SELECT * FROM opportunities WHERE opportunity_id = ?",
                (opp_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_opportunity(self, opportunity_id: str) -> Optional[dict]:
        """获取单个 Opportunity"""
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM opportunities WHERE opportunity_id = ?",
                (opportunity_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_opportunities(
        self,
        enterprise_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        """按条件筛选 Opportunity 列表"""
        conditions = []
        params = []
        if enterprise_id:
            conditions.append("enterprise_id = ?")
            params.append(enterprise_id)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM opportunities {where} ORDER BY created_at DESC",
                params,
            ).fetchall()
            return [dict(r) for r in rows]

    def update_opportunity_status(
        self,
        opportunity_id: str,
        new_status: str,
        event_type: str = "status_change",
        note: str = "",
    ) -> Optional[dict]:
        """
        推进 Opportunity 状态 + 写事件日志

        状态机规则:
        discovered → applying → submitted → approved/rejected
        只有向前推进才允许（不能回退）
        """
        valid_transitions = {
            "discovered": ["applying"],
            "applying": ["submitted"],
            "submitted": ["approved", "rejected"],
            "approved": [],
            "rejected": [],
        }

        with self.get_conn() as conn:
            current = conn.execute(
                "SELECT status FROM opportunities WHERE opportunity_id = ?",
                (opportunity_id,),
            ).fetchone()
            if not current:
                return None

            old_status = current["status"]
            if new_status not in valid_transitions.get(old_status, []):
                raise ValueError(
                    f"非法状态转换: {old_status} → {new_status}，"
                    f"允许: {valid_transitions.get(old_status, [])}"
                )

            conn.execute(
                "UPDATE opportunities SET status = ?, updated_at = datetime('now', 'localtime') WHERE opportunity_id = ?",
                (new_status, opportunity_id),
            )

            # 写事件日志
            import uuid
            conn.execute("""INSERT INTO opportunity_events
                (event_id, opportunity_id, event_type, old_status, new_status, note)
                VALUES (?, ?, ?, ?, ?, ?)""", (
                    str(uuid.uuid4()),
                    opportunity_id,
                    event_type,
                    old_status,
                    new_status,
                    note,
                ))

            row = conn.execute(
                "SELECT * FROM opportunities WHERE opportunity_id = ?",
                (opportunity_id,),
            ).fetchone()
            return dict(row) if row else None

    def delete_opportunity(self, opportunity_id: str) -> bool:
        """删除 Opportunity（仅 discovered/applying 状态可删）"""
        with self.get_conn() as conn:
            current = conn.execute(
                "SELECT status FROM opportunities WHERE opportunity_id = ?",
                (opportunity_id,),
            ).fetchone()
            if not current:
                return False
            if current["status"] not in ("discovered", "applying"):
                raise ValueError(f"状态 {current['status']} 的 Opportunity 不可删除")

            # 级联删除材料 + 事件
            conn.execute("DELETE FROM material_checklist WHERE opportunity_id = ?", (opportunity_id,))
            conn.execute("DELETE FROM opportunity_events WHERE opportunity_id = ?", (opportunity_id,))
            conn.execute("DELETE FROM opportunities WHERE opportunity_id = ?", (opportunity_id,))
            return True

    # ══════════════════════════════════════════
    # Opportunity Events
    # ══════════════════════════════════════════

    def list_opportunity_events(self, opportunity_id: str) -> list[dict]:
        """获取 Opportunity 操作时间线"""
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM opportunity_events WHERE opportunity_id = ? ORDER BY created_at",
                (opportunity_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ══════════════════════════════════════════
    # Material Checklist
    # ══════════════════════════════════════════

    def add_materials(self, opportunity_id: str, materials: list[dict]) -> list[dict]:
        """批量添加材料项（去重：同名材料只保留一条，不重复插入）"""
        import uuid
        results = []
        with self.get_conn() as conn:
            # 查出已有的材料名
            existing = {
                r[0] for r in conn.execute(
                    "SELECT material_name FROM material_checklist WHERE opportunity_id = ?",
                    (opportunity_id,)
                ).fetchall()
            }
            for mat in materials:
                material_name = mat["material_name"]
                # 跳过已存在的同名材料
                if material_name in existing:
                    continue
                mat_id = str(uuid.uuid4())
                conn.execute("""INSERT INTO material_checklist
                    (material_id, opportunity_id, material_name, status, notes, source)
                    VALUES (?, ?, ?, ?, ?, ?)""", (
                        mat_id,
                        opportunity_id,
                        material_name,
                        mat.get("status", "preparing"),
                        mat.get("notes", ""),
                        mat.get("source", "kg"),
                    ))
                existing.add(material_name)
                results.append({
                    "material_id": mat_id,
                    "opportunity_id": opportunity_id,
                    "material_name": material_name,
                    "status": mat.get("status", "preparing"),
                    "notes": mat.get("notes", ""),
                    "source": mat.get("source", "kg"),
                })
        return results

    def list_materials(self, opportunity_id: str) -> list[dict]:
        """获取材料清单"""
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM material_checklist WHERE opportunity_id = ? ORDER BY created_at",
                (opportunity_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_material(self, material_id: str) -> Optional[dict]:
        """获取单个材料项"""
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM material_checklist WHERE material_id = ?",
                (material_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_material(self, material_id: str, status: Optional[str] = None, notes: Optional[str] = None) -> Optional[dict]:
        """更新材料项状态/备注"""
        updates = []
        params = []
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if not updates:
            return self.get_material(material_id)

        updates.append("updated_at = datetime('now', 'localtime')")
        params.append(material_id)

        with self.get_conn() as conn:
            conn.execute(
                f"UPDATE material_checklist SET {', '.join(updates)} WHERE material_id = ?",
                params,
            )
        return self.get_material(material_id)

    def delete_materials_by_opportunity(self, opportunity_id: str) -> int:
        """删除某个 Opportunity 的全部材料"""
        with self.get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM material_checklist WHERE opportunity_id = ?",
                (opportunity_id,),
            )
            return cursor.rowcount

    def get_materials_progress(self, opportunity_id: str) -> dict:
        """计算材料完成度"""
        materials = self.list_materials(opportunity_id)
        if not materials:
            return {"total": 0, "ready_count": 0, "progress_pct": 0.0}
        ready_count = sum(1 for m in materials if m["status"] in ("ready", "submitted", "waived"))
        return {
            "total": len(materials),
            "ready_count": ready_count,
            "progress_pct": round(ready_count / len(materials) * 100, 1),
        }

    # ══════════════════════════════════════════
    # Generated Documents
    # ══════════════════════════════════════════

    def add_generated_document(self, doc: dict) -> dict:
        """添加生成的文档记录"""
        with self.get_conn() as conn:
            conn.execute("""INSERT INTO generated_documents
                (doc_id, opportunity_id, material_id, doc_name, doc_type, file_path, file_size, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (
                    doc["doc_id"],
                    doc["opportunity_id"],
                    doc.get("material_id", ""),
                    doc["doc_name"],
                    doc.get("doc_type", "docx"),
                    doc["file_path"],
                    doc.get("file_size", 0),
                    doc.get("status", "generated"),
                ))
            row = conn.execute(
                "SELECT * FROM generated_documents WHERE doc_id = ?",
                (doc["doc_id"],),
            ).fetchone()
            return dict(row) if row else None

    def list_generated_documents(self, opportunity_id: str) -> list[dict]:
        """获取某个 Opportunity 的全部生成文档"""
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM generated_documents WHERE opportunity_id = ? ORDER BY created_at",
                (opportunity_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_generated_document(self, doc_id: str) -> Optional[dict]:
        """获取单个生成文档"""
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM generated_documents WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            return dict(row) if row else None

    def delete_generated_documents_by_opportunity(self, opportunity_id: str) -> int:
        """删除某个 Opportunity 的全部生成文档"""
        with self.get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM generated_documents WHERE opportunity_id = ?",
                (opportunity_id,),
            )
            return cursor.rowcount

    # ══════════════════════════════════════════
    # Submission Packages
    # ══════════════════════════════════════════

    def upsert_submission_package(self, pkg: dict) -> dict:
        """创建或更新申报包"""
        opp_id = pkg["opportunity_id"]
        with self.get_conn() as conn:
            existing = conn.execute(
                "SELECT package_id FROM submission_packages WHERE opportunity_id = ?",
                (opp_id,),
            ).fetchone()

            if existing:
                conn.execute("""UPDATE submission_packages SET
                    status = ?,
                    materials_checklist_json = ?,
                    documents_json = ?,
                    profile_snapshot_json = ?,
                    policy_snapshot_json = ?,
                    submission_strategy = ?,
                    confirmed_by = ?,
                    confirmed_at = ?,
                    submitted_at = ?,
                    updated_at = datetime('now', 'localtime')
                WHERE opportunity_id = ?""", (
                    pkg.get("status", "preparing"),
                    pkg.get("materials_checklist_json", "[]"),
                    pkg.get("documents_json", "[]"),
                    pkg.get("profile_snapshot_json", "{}"),
                    pkg.get("policy_snapshot_json", "{}"),
                    pkg.get("submission_strategy", "manual"),
                    pkg.get("confirmed_by", ""),
                    pkg.get("confirmed_at", ""),
                    pkg.get("submitted_at", ""),
                    opp_id,
                ))
                pkg_id = existing["package_id"]
            else:
                import uuid
                pkg_id = pkg.get("package_id", str(uuid.uuid4()))
                conn.execute("""INSERT INTO submission_packages
                    (package_id, opportunity_id, status,
                     materials_checklist_json, documents_json,
                     profile_snapshot_json, policy_snapshot_json,
                     submission_strategy, confirmed_by, confirmed_at, submitted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                        pkg_id,
                        opp_id,
                        pkg.get("status", "preparing"),
                        pkg.get("materials_checklist_json", "[]"),
                        pkg.get("documents_json", "[]"),
                        pkg.get("profile_snapshot_json", "{}"),
                        pkg.get("policy_snapshot_json", "{}"),
                        pkg.get("submission_strategy", "manual"),
                        pkg.get("confirmed_by", ""),
                        pkg.get("confirmed_at", ""),
                        pkg.get("submitted_at", ""),
                    ))

            row = conn.execute(
                "SELECT * FROM submission_packages WHERE package_id = ?",
                (pkg_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_submission_package(self, opportunity_id: str) -> Optional[dict]:
        """获取申报包"""
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM submission_packages WHERE opportunity_id = ?",
                (opportunity_id,),
            ).fetchone()
            return dict(row) if row else None

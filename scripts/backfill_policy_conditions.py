"""
补数据脚本：把现有 Condition 节点反向同步到 Policy 直接属性

Phase 4.2: Policy 节点新增 regions/company_types/industries 属性，
需要从已有的 has_eligibility 边对应的 Condition 节点反向填充。

用法：
    python scripts/backfill_policy_conditions.py
"""

import sys
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger
from src.storage.neo4j_store import Neo4jStore
from config.settings import settings


def backfill_policy_conditions():
    """从 Condition 节点反向同步到 Policy 直接属性"""
    store = Neo4jStore(
        uri=settings.NEO4J_URI,
        user=settings.NEO4J_USER,
        password=settings.NEO4J_PASSWORD,
        database=settings.NEO4J_DATABASE,
    )

    with store.driver.session(database=store.database) as session:
        # 1. 查询所有有 has_eligibility 边的 Policy，聚合条件
        result = session.run("""
            MATCH (p:Policy)-[:has_eligibility]->(c:Condition)
            WHERE p.status IS NULL OR p.status <> 'repealed'
            WITH p, c
            ORDER BY c.category
            WITH p,
                 collect(DISTINCT CASE WHEN c.category = 'region' THEN c.name END) AS regions,
                 collect(DISTINCT CASE WHEN c.category = 'company_type' THEN c.name END) AS company_types,
                 collect(DISTINCT CASE WHEN c.category = 'industry' THEN c.name END) AS industries
            WITH p,
                 [r IN regions WHERE r IS NOT NULL] AS clean_regions,
                 [ct IN company_types WHERE ct IS NOT NULL] AS clean_company_types,
                 [ind IN industries WHERE ind IS NOT NULL] AS clean_industries
            RETURN p.name AS policy_name,
                   clean_regions AS regions,
                   clean_company_types AS company_types,
                   clean_industries AS industries
        """)

        updated = 0
        skipped = 0
        for record in result:
            policy_name = record["policy_name"]
            regions = record["regions"]
            company_types = record["company_types"]
            industries = record["industries"]

            if not regions and not company_types and not industries:
                skipped += 1
                continue

            # 2. SET Policy 直接属性
            session.run(
                """MATCH (p:Policy {name: $name})
                SET p.regions = $regions,
                    p.company_types = $company_types,
                    p.industries = $industries,
                    p.region = CASE WHEN size($regions) > 0 THEN $regions[0] ELSE null END,
                    p.company_type = CASE WHEN size($company_types) > 0 THEN $company_types[0] ELSE null END,
                    p.industry = CASE WHEN size($industries) > 0 THEN $industries[0] ELSE null END
                """,
                name=policy_name,
                regions=regions,
                company_types=company_types,
                industries=industries,
            )
            updated += 1
            logger.info(
                f"✅ {policy_name[:50]}: "
                f"regions={regions}, "
                f"company_types={company_types}, "
                f"industries={industries}"
            )

        logger.info(f"\n📊 补数据完成: {updated} 个 Policy 更新, {skipped} 个跳过(无条件)")

        # 3. 统计
        stats = session.run("""
            MATCH (p:Policy)
            WHERE p.regions IS NOT NULL OR p.company_types IS NOT NULL OR p.industries IS NOT NULL
            RETURN count(p) AS with_attrs
        """).single()
        logger.info(f"  有直接条件的 Policy 数: {stats['with_attrs']}")

    store.close()


if __name__ == "__main__":
    logger.info("开始补数据: Condition → Policy 直接属性...")
    backfill_policy_conditions()

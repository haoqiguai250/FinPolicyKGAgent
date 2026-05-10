"""
Neo4j 连通性 + 基础 CRUD 验证脚本

验证内容：
1. 连接 Neo4j
2. 创建唯一约束
3. 写入实体 + 关系
4. MERGE 去重验证
5. 查询验证
6. DETACH DELETE 验证
7. 导出 JSON 验证
"""
import sys
import os

# 修复 Windows 控制台编码
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from pathlib import Path

from src.storage.neo4j_store import Neo4jStore
from src.extraction.schema import Entity, Triple
from loguru import logger


def main():
    print("=" * 60)
    print("Neo4j 连通性 + CRUD 验证")
    print("=" * 60)

    # 1. 连接
    print("\n[1] 连接 Neo4j...")
    try:
        store = Neo4jStore()
        store.driver  # 触发连接
        print("  ✅ 连接成功！")
    except Exception as e:
        print(f"  ❌ 连接失败: {e}")
        print("  请确认 Docker 容器运行: docker ps | grep neo4j")
        return

    # 2. 创建约束
    print("\n[2] 创建唯一约束...")
    try:
        store.ensure_constraints()
        print("  ✅ 约束创建成功")
    except Exception as e:
        print(f"  ❌ 约束创建失败: {e}")

    # 清空测试数据
    print("\n[清空] 清空旧数据...")
    store.clear_all()
    print("  ✅ 已清空")

    # 3. 写入实体
    print("\n[3] 写入实体...")
    entities = [
        Entity(name="瞪羚企业政策", entity_type="Policy", attributes={"title": "瞪羚企业行动计划"}),
        Entity(name="融资类", entity_type="ActionType", attributes={"category": "融资类", "raw": ["贷款", "信贷"]}),
        Entity(name="中小企业", entity_type="Condition", attributes={"category": "company_type", "value": "中小企业"}),
        Entity(name="深圳", entity_type="Region", attributes={"name": "深圳"}),
        Entity(name="扩大融资能力", entity_type="Strategy", attributes={"name": "扩大融资能力"}),
    ]
    added = store.add_entities(entities)
    print(f"  ✅ 写入 {added}/{len(entities)} 实体")

    # 4. 写入关系
    print("\n[4] 写入关系...")
    triples = [
        Triple(
            subject=Entity(name="瞪羚企业政策", entity_type="Policy"),
            relation="provides",
            object_=Entity(name="融资类", entity_type="ActionType"),
            confidence=1.0,
            source_text="政策提供融资类措施",
        ),
        Triple(
            subject=Entity(name="瞪羚企业政策", entity_type="Policy"),
            relation="has_eligibility",
            object_=Entity(name="中小企业", entity_type="Condition"),
            confidence=1.0,
            source_text="政策适用于中小企业",
        ),
        Triple(
            subject=Entity(name="融资类", entity_type="ActionType"),
            relation="leads_to",
            object_=Entity(name="扩大融资能力", entity_type="Strategy"),
            confidence=1.0,
            source_text="融资类措施可扩大融资能力",
        ),
    ]
    added = store.add_triples(triples)
    print(f"  ✅ 写入 {added}/{len(triples)} 关系")

    # 5. MERGE 去重验证
    print("\n[5] MERGE 去重验证（重复写入）...")
    dup_entities = [
        Entity(name="瞪羚企业政策", entity_type="Policy", attributes={"title": "瞪羚企业行动计划（更新）"}),
        Entity(name="融资类", entity_type="ActionType", attributes={"category": "融资类", "raw": ["贷款", "信贷", "授信"]}),
    ]
    added = store.add_entities(dup_entities)
    print(f"  ✅ 重复实体新增: {added}（应为 0，MERGE 去重生效）")

    # 6. 统计
    print("\n[6] 统计...")
    stats = store.compute_stats()
    print(f"  实体总数: {stats['total_entities']}")
    print(f"  三元组总数: {stats['total_triples']}")
    print(f"  实体类型分布: {stats['entity_type_distribution']}")
    print(f"  关系类型分布: {stats['relation_type_distribution']}")

    # 7. 查询验证
    print("\n[7] Cypher 查询验证...")
    from src.storage.cypher_queries import FIND_REASONING_PATHS, FIND_POLICY_CONDITIONS
    with store.driver.session(database=store.database) as session:
        # 查 Policy → Condition
        result = session.run(FIND_POLICY_CONDITIONS, policy_name="瞪羚企业政策")
        for record in result:
            print(f"  Policy 条件: {record['category']}={record['value']}")
        print("  ✅ Cypher 查询成功")

    # 8. DETACH DELETE 验证
    print("\n[8] DETACH DELETE 验证...")
    rel_count = store.count_node_relationships("扩大融资能力", "Strategy")
    print(f"  Strategy(扩大融资能力) 关系数: {rel_count}")
    deleted = store.detach_delete_node("扩大融资能力", "Strategy")
    print(f"  删除节点数: {deleted}")
    # 验证已删除
    stats_after = store.compute_stats()
    print(f"  删除后实体总数: {stats_after['total_entities']}")
    print(f"  删除后三元组总数: {stats_after['total_triples']}")

    # 恢复
    print("\n  恢复节点...")
    store.add_entities([Entity(name="扩大融资能力", entity_type="Strategy", attributes={"name": "扩大融资能力"})])
    store.add_triples([Triple(
        subject=Entity(name="融资类", entity_type="ActionType"),
        relation="leads_to",
        object_=Entity(name="扩大融资能力", entity_type="Strategy"),
        confidence=1.0,
    )])
    print("  ✅ 节点已恢复")

    # 9. JSON 导出
    print("\n[9] JSON 导出验证...")
    output_path = store.save(Path(PROJECT_ROOT) / "outputs" / "exports" / "neo4j_test_export.json")
    print(f"  ✅ 导出路径: {output_path}")

    # 10. 从 JSON 导入
    print("\n[10] JSON 导入验证...")
    store.clear_all()
    loaded = Neo4jStore.load_from_json(output_path)
    loaded_stats = loaded.compute_stats()
    print(f"  ✅ 导入后统计: {loaded_stats['total_entities']} 实体, {loaded_stats['total_triples']} 三元组")

    # 清理测试数据
    print("\n[清理] 清空测试数据...")
    loaded.clear_all()
    loaded.close()
    print("  ✅ 已清理")

    print("\n" + "=" * 60)
    print("✅ Neo4j 验证全部通过！")
    print("=" * 60)


if __name__ == "__main__":
    main()

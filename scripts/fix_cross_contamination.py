"""修复研发投入补助 PDF 的条件交叉污染"""
from neo4j import GraphDatabase

d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','finagent2026'))

MASTER = '深圳市科技创新局关于印发《深圳市研发投入补助计划项目管理办法》的通知'

# 需要删除的污染条件名
POLLUTED_CONDITIONS = [
    '印染、电镀、皮革、线路板和其他严重污染环境的行业',
    '饮用水源保护区、自然保护区和其他环境保护特殊区域',
    '小微企业',
    '资助对象条件-机构',
    '资助对象条件-企业',
]

with d.session() as s:
    # 1. 删除 MasterPolicy 直连的污染条件
    print('=== 删除 MasterPolicy 直连污染条件 ===')
    for cond_name in POLLUTED_CONDITIONS:
        r = s.run("""
            MATCH (mp:Policy {name: $master_name})-[rel:has_eligibility]->(c:Condition {name: $cond_name})
            DELETE rel
            RETURN count(rel) as deleted
        """, master_name=MASTER, cond_name=cond_name).single()
        if r and r['deleted'] > 0:
            print(f'  ✅ 删除 {cond_name[:40]}')

    # 2. 删除 contains 子政策链路上的污染条件
    print()
    print('=== 删除子政策污染条件 ===')
    result = s.run("""
        MATCH (mp:Policy {name: $master_name})-[:contains]->(child:Policy)-[rel:has_eligibility]->(c:Condition)
        RETURN child.name as cn, c.name as cond, id(rel) as rid
    """, master_name=MASTER)
    
    deleted_count = 0
    for row in result:
        cond = row['cond']
        should_delete = any(p in cond for p in ['印染', '饮用水源', '小微', '资助对象条件'])
        if should_delete:
            s.run("MATCH ()-[r]-() WHERE id(r) = $rid DELETE r", rid=row['rid'])
            print(f'  ✅ 删除 [{row["cn"][:20]}] -[{cond[:50]}]')
            deleted_count += 1
    print(f'  共删除 {deleted_count} 条')

    # 3. 添加 region=深圳
    print()
    print('=== 添加 region=深圳 ===')
    sz_exists = s.run(
        "MATCH (c:Condition {name: '深圳', category: 'region'}) RETURN c"
    ).single()
    if not sz_exists:
        s.run("CREATE (c:Condition {name: '深圳', category: 'region', value: '深圳'})")
        print('  ✅ 创建 Condition: 深圳')

    s.run("""
        MATCH (mp:Policy {name: $master_name}), (c:Condition {name: '深圳', category: 'region'})
        MERGE (mp)-[r:has_eligibility]->(c)
        SET r.source_text = '注册地在深圳市'
    """, master_name=MASTER)
    print('  ✅ 添加 MasterPolicy -[has_eligibility]-> 深圳')

    # 4. 验证
    print()
    print('=== 修复后条件 ===')
    for r in s.run("""
        MATCH (mp:Policy {name: $master_name})-[:has_eligibility]->(c:Condition)
        RETURN c.name, c.category
    """, master_name=MASTER):
        print(f'  [{r["c.category"]}] {r["c.name"][:60]}')

d.close()
print()
print('✅ 修复完成')

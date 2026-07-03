"""修复 Region 层级关系 — 添加深圳各区 subregion_of 边"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.neo4j_store import Neo4jStore
from config.settings import settings

store = Neo4jStore(
    uri=settings.NEO4J_URI,
    user=settings.NEO4J_USER,
    password=settings.NEO4J_PASSWORD,
    database=settings.NEO4J_DATABASE,
)

subregion_map = {
    "深圳": ["坪山区", "坪山", "南山区", "福田区", "罗湖区", "宝安区", "龙岗区", "龙华区", "光明区", "盐田区", "大鹏新区", "深汕特别合作区"],
    "广东": ["深圳", "广州", "东莞", "佛山", "惠州", "珠海", "中山"],
    "中国": ["广东", "北京", "上海", "浙江", "江苏", "四川"],
}

with store.driver.session(database=store.database) as session:
    created = 0
    for parent, children in subregion_map.items():
        for child in children:
            r = session.run(
                "MATCH (c:Region {name: $child})-[rel:subregion_of]->(p:Region {name: $parent}) "
                "RETURN count(rel) AS cnt",
                child=child, parent=parent,
            ).single()
            if not r or r["cnt"] == 0:
                session.run("MERGE (r:Region {name: $name})", name=child)
                session.run(
                    "MATCH (c:Region {name: $child}) "
                    "MATCH (p:Region {name: $parent}) "
                    "MERGE (c)-[:subregion_of]->(p)",
                    child=child, parent=parent,
                )
                created += 1
                print(f"  + {child} → {parent}")

    print(f"\n✅ 创建了 {created} 条 subregion_of 关系")

    r = session.run("MATCH ()-[rel:subregion_of]->() RETURN count(rel) AS cnt").single()
    print(f"现在 subregion_of 关系: {r['cnt']} 条")

store.close()

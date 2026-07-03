"""备份当前 Neo4j 到 JSON 文件"""
import sys, json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.neo4j_store import Neo4jStore
from config.settings import settings

BACKUP_DIR = Path("data/backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

store = Neo4jStore(
    uri=settings.NEO4J_URI, user=settings.NEO4J_USER,
    password=settings.NEO4J_PASSWORD, database=settings.NEO4J_DATABASE,
)

output = BACKUP_DIR / f"neo4j_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

with store.driver.session(database=store.database) as session:
    # 节点
    print("导出节点...")
    nodes = [{"labels": list(r["labels"]), "props": dict(r["props"])}
             for r in session.run("MATCH (n) RETURN labels(n) AS labels, properties(n) AS props")]
    print(f"  {len(nodes)} 个节点")

    # 关系
    print("导出关系...")
    rels = [{
        "type": r["type"], "props": dict(r["props"]),
        "start_labels": list(r["start_labels"]), "start_name": r["start_name"],
        "end_labels": list(r["end_labels"]), "end_name": r["end_name"],
    } for r in session.run("""
        MATCH (s)-[r]->(e)
        RETURN type(r) AS type, properties(r) AS props,
               labels(s) AS start_labels, s.name AS start_name,
               labels(e) AS end_labels, e.name AS end_name
    """)]
    print(f"  {len(rels)} 条关系")

    backup = {
        "time": datetime.now().isoformat(),
        "stats": store.compute_stats(),
        "nodes": nodes,
        "relationships": rels,
    }

with open(output, "w", encoding="utf-8") as f:
    json.dump(backup, f, ensure_ascii=False, default=str)

stats = store.compute_stats()
print(f"\n✅ 备份完成: {output}")
print(f"   文件: {output.stat().st_size / 1024:.0f} KB")
print(f"   节点: {stats['total_entities']}, 关系: {stats['total_triples']}")

store.close()

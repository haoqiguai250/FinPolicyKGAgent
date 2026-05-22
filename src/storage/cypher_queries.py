"""
Cypher 查询模板

集中管理所有 Neo4j Cypher 语句，方便维护和复用
"""

# ══════════════════════════════════════════
# 唯一约束（初始化时执行）
# ══════════════════════════════════════════

CONSTRAINT_QUERIES = {
    "Policy": "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Policy) REQUIRE n.name IS UNIQUE",
    "Institution": "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Institution) REQUIRE n.name IS UNIQUE",
    "FinancialConcept": "CREATE CONSTRAINT IF NOT EXISTS FOR (n:FinancialConcept) REQUIRE n.name IS UNIQUE",
    "Market": "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Market) REQUIRE n.name IS UNIQUE",
    "Event": "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Event) REQUIRE n.name IS UNIQUE",
    "Indicator": "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Indicator) REQUIRE n.name IS UNIQUE",
    "Person": "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Person) REQUIRE n.name IS UNIQUE",
    "Document": "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Document) REQUIRE n.name IS UNIQUE",
    "ActionType": "CREATE CONSTRAINT IF NOT EXISTS FOR (n:ActionType) REQUIRE n.name IS UNIQUE",
    "Condition": "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Condition) REQUIRE n.name IS UNIQUE",
    "Strategy": "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Strategy) REQUIRE n.name IS UNIQUE",
    "Region": "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Region) REQUIRE n.name IS UNIQUE",
    "CompanyType": "CREATE CONSTRAINT IF NOT EXISTS FOR (n:CompanyType) REQUIRE n.name IS UNIQUE",
    "Industry": "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Industry) REQUIRE n.name IS UNIQUE",
}


# ══════════════════════════════════════════
# MERGE 节点（去重写入）
# ══════════════════════════════════════════

MERGE_NODE = """
MERGE (n:$label {name: $name})
SET n += $props
RETURN n
"""

# 动态拼接版（用于不同 label）
MERGE_NODE_TEMPLATE = """
MERGE (n:{label} {{name: $name}})
SET n += $props
RETURN n
"""


# ══════════════════════════════════════════
# MERGE 关系（去重写入）
# ══════════════════════════════════════════

MERGE_RELATION_TEMPLATE = """
MATCH (s:{subj_label} {{name: $subj_name}})
MATCH (o:{obj_label} {{name: $obj_name}})
MERGE (s)-[r:{rel_type}]->(o)
SET r += $props
RETURN r
"""


# ══════════════════════════════════════════
# 统计查询
# ══════════════════════════════════════════

COUNT_ALL_NODES = """
MATCH (n)
RETURN labels(n)[0] AS label, count(n) AS count
ORDER BY count DESC
"""

COUNT_ALL_RELATIONSHIPS = """
MATCH ()-[r]->()
RETURN type(r) AS rel_type, count(r) AS count
ORDER BY count DESC
"""

COUNT_TOTAL_NODES = "MATCH (n) RETURN count(n) AS total"
COUNT_TOTAL_RELATIONSHIPS = "MATCH ()-[r]->() RETURN count(r) AS total"


# ══════════════════════════════════════════
# 推理路径查询（决策支持核心）
# ══════════════════════════════════════════

# Company → Condition ← Policy → ActionType → Strategy
FIND_REASONING_PATHS = """
MATCH (p:Policy)-[:has_eligibility]->(c:Condition)
WHERE c.category IN $condition_categories
  AND c.name IN $condition_values
WITH DISTINCT p
MATCH (p)-[:provides]->(a:ActionType)
OPTIONAL MATCH (a)-[:leads_to]->(s:Strategy)
RETURN p.name AS policy_name,
       a.name AS action_type,
       a.raw AS action_raw,
       collect(DISTINCT s.name) AS strategies
"""

# 按 Condition 精确匹配 Policy
# D1: 加 status 过滤，排除废止政策
FIND_POLICIES_BY_CONDITIONS = """
MATCH (p:Policy)-[:has_eligibility]->(c:Condition)
WHERE p.status IS NULL OR p.status <> 'repealed'
WITH p, collect({category: c.category, value: c.name}) AS policy_conds
WITH p, policy_conds,
     [cond IN policy_conds WHERE cond.category = 'region' | cond.value] AS region_conds,
     [cond IN policy_conds WHERE cond.category = 'company_type' | cond.value] AS type_conds,
     [cond IN policy_conds WHERE cond.category = 'industry' | cond.value] AS industry_conds
RETURN p.name AS policy_name, policy_conds, region_conds, type_conds, industry_conds
"""

# Region 层级扩展：向上查找所有祖先
FIND_REGION_ANCESTORS = """
MATCH (r:Region {name: $region_name})
CALL {
    WITH r
    MATCH path = (r)-[:subregion_of*]->(ancestor)
    RETURN ancestor.name AS ancestor_name
}
RETURN collect(r.name) + collect(ancestor_name) AS region_chain
"""

# 获取 Policy 的所有 Condition
FIND_POLICY_CONDITIONS = """
MATCH (p:Policy {name: $policy_name})-[r:has_eligibility]->(c:Condition)
RETURN c.category AS category, c.name AS value,
       r.source_text AS eligibility_source_text
"""

# 获取 Policy 的所有 ActionType
# D2: 加 raw_relation 读取
FIND_POLICY_ACTIONS = """
MATCH (p:Policy {name: $policy_name})-[r:provides]->(a:ActionType)
RETURN a.name AS action_type, a.raw AS action_raw, 
       r.source_chunk_id AS provides_chunk_id,
       r.source_text AS provides_source_text,
       r.raw_relation AS provides_raw_relation
"""

# 获取 ActionType 的 Strategy
FIND_ACTION_STRATEGIES = """
MATCH (a:ActionType {name: $action_type})-[r:leads_to]->(s:Strategy)
RETURN s.name AS strategy, r.source_chunk_id AS leads_to_chunk_id,
       r.source_text AS leads_to_source_text
"""


# ══════════════════════════════════════════
# 图扰动查询
# ══════════════════════════════════════════

# 扰动：删除节点及其所有关系（事务中执行）
DETACH_DELETE_NODE = """
MATCH (n)
WHERE n.name = $name AND $label IN labels(n)
DETACH DELETE n
RETURN count(n) AS deleted
"""

# 查询节点参与的关系数
COUNT_NODE_RELATIONSHIPS = """
MATCH (n)-[r]-()
WHERE n.name = $name AND $label IN labels(n)
RETURN count(r) AS rel_count
"""

# 恢复节点（重新写入）
# 使用 MERGE_NODE_TEMPLATE + MERGE_RELATION_TEMPLATE


# ══════════════════════════════════════════
# 全量导出（JSON 备份）
# ══════════════════════════════════════════

EXPORT_ALL_NODES = """
MATCH (n)
RETURN labels(n)[0] AS type, n.name AS name, properties(n) AS attributes
"""

EXPORT_ALL_RELATIONSHIPS = """
MATCH (s)-[r]->(o)
RETURN labels(s)[0] AS subj_type, s.name AS subj_name,
       type(r) AS relation, properties(r) AS rel_props,
       labels(o)[0] AS obj_type, o.name AS obj_name
"""


# ══════════════════════════════════════════
# 时序化查询（D3/D4）
# ══════════════════════════════════════════

# D3: 查询某政策的废止链（递归）
FIND_REPEAL_CHAIN = """
MATCH (p:Policy {name: $policy_name})-[:repeals*]->(old:Policy)
RETURN old.name AS repealed_policy, old.repealed_at AS repealed_at
"""

# D4: 查询某政策被哪个政策废止
FIND_REPEALED_BY = """
MATCH (new:Policy)-[:repeals]->(p:Policy {name: $policy_name})
RETURN new.name AS repealed_by, new.effective_date AS replacement_date
"""

# 按 source_file 查询 Policy 名称（推送模式），D8: 加 status 过滤
FIND_POLICY_NAMES_BY_SOURCE_FILE = """
MATCH (p:Policy)
WHERE p.source_file = $source_file
  AND (p.status IS NULL OR p.status <> 'repealed')
RETURN p.name AS name
"""

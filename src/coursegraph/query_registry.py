from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QuerySpec:
    description: str
    cypher: str
    required_params: frozenset[str]
    optional_params: dict[str, Any] = field(default_factory=dict)


# Only these reviewed, parameterized, read-only statements can reach Neo4j.
QUERY_REGISTRY: dict[str, QuerySpec] = {
    "course_details": QuerySpec(
        description="Fetch one course and its direct prerequisites.",
        cypher="""
        MATCH (c:Course {code: $code})
        OPTIONAL MATCH (c)-[:REQUIRES]->(p:Course)
        RETURN c.code AS code, c.title AS title, c.department AS department,
               c.level AS level, c.credits AS credits,
               collect(DISTINCT p.code) AS prerequisites
        """,
        required_params=frozenset({"code"}),
    ),
    "prerequisites": QuerySpec(
        description="Traverse every prerequisite path for a course.",
        cypher="""
        MATCH (c:Course {code: $code})
        OPTIONAL MATCH p=(c)-[:REQUIRES*1..8]->(required:Course)
        WHERE required IS NULL OR NOT (required)-[:REQUIRES]->(:Course)
        RETURN c.code AS course,
               CASE WHEN p IS NULL THEN [c.code] ELSE [n IN nodes(p) | n.code] END AS path
        ORDER BY size(path), path
        """,
        required_params=frozenset({"code"}),
    ),
    "unlocks": QuerySpec(
        description="Find courses unlocked directly or transitively by one course.",
        cypher="""
        MATCH p=(start:Course {code: $code})<-[:REQUIRES*1..8]-(unlocked:Course)
        RETURN unlocked.code AS code, unlocked.title AS title,
               [n IN nodes(p) | n.code] AS path
        ORDER BY size(path), unlocked.code
        """,
        required_params=frozenset({"code"}),
    ),
    "shortest_path": QuerySpec(
        description="Find the shortest prerequisite connection between two courses.",
        cypher="""
        MATCH (a:Course {code: $from_code}), (b:Course {code: $to_code})
        OPTIONAL MATCH p=shortestPath((a)-[:REQUIRES*..8]-(b))
        RETURN a.code AS from_code, b.code AS to_code,
               CASE WHEN p IS NULL THEN [] ELSE [n IN nodes(p) | n.code] END AS path
        """,
        required_params=frozenset({"from_code", "to_code"}),
    ),
    "courses_by_department": QuerySpec(
        description="List courses in a department at or above a level.",
        cypher="""
        MATCH (c:Course {department: $department})
        WHERE c.level >= $level_min
        RETURN c.code AS code, c.title AS title, c.level AS level
        ORDER BY c.level, c.code
        LIMIT $limit
        """,
        required_params=frozenset({"department"}),
        optional_params={"level_min": 0, "limit": 20},
    ),
    "topic_courses": QuerySpec(
        description="Find courses whose catalog topics include a term.",
        cypher="""
        MATCH (c:Course)
        WHERE toLower(c.topics_text) CONTAINS toLower($topic)
        RETURN c.code AS code, c.title AS title, c.level AS level
        ORDER BY c.level, c.code
        LIMIT $limit
        """,
        required_params=frozenset({"topic"}),
        optional_params={"limit": 20},
    ),
    "program_requirements": QuerySpec(
        description="List the courses and offering constraints for a modeled academic program.",
        cypher="""
        MATCH (p:Program {code: $program_code})-[:REQUIRES_COURSE]->(c:Course)
        RETURN p.code AS program_code, p.title AS program_title,
               c.code AS code, c.title AS title, c.credits AS credits,
               c.offered_terms AS offered_terms
        ORDER BY c.level, c.code
        """,
        required_params=frozenset({"program_code"}),
    ),
}


def validated_query(query_id: str, params: dict[str, Any]) -> tuple[QuerySpec, dict[str, Any]]:
    if query_id not in QUERY_REGISTRY:
        allowed = ", ".join(sorted(QUERY_REGISTRY))
        raise ValueError(f"Unknown query_id '{query_id}'. Allowed queries: {allowed}")
    spec = QUERY_REGISTRY[query_id]
    supplied = set(params)
    allowed_params = spec.required_params | set(spec.optional_params)
    missing = spec.required_params - supplied
    unexpected = supplied - allowed_params
    if missing:
        raise ValueError(f"Missing parameters for {query_id}: {', '.join(sorted(missing))}")
    if unexpected:
        raise ValueError(f"Unexpected parameters for {query_id}: {', '.join(sorted(unexpected))}")
    safe_params = {**spec.optional_params, **params}
    for key, value in list(safe_params.items()):
        if key.endswith("code") or key == "code":
            safe_params[key] = str(value).upper().strip()
        if key == "department":
            safe_params[key] = str(value).upper().strip()
    if "limit" in safe_params:
        safe_params["limit"] = max(1, min(int(safe_params["limit"]), 50))
    if "level_min" in safe_params:
        safe_params["level_min"] = max(0, min(int(safe_params["level_min"]), 900))
    return spec, safe_params

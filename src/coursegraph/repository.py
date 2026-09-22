from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import deque
from typing import Any, Iterable

from neo4j import GraphDatabase

from coursegraph.catalog import courses, prerequisite_map, sources
from coursegraph.models import Citation, Course, GraphPath, Source
from coursegraph.programs import get_program, offering_terms, program_requirement_rows, program_rows
from coursegraph.query_registry import validated_query


def _normalise_codes(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value).upper().strip() for value in values if value))


def _citation(source: Source) -> Citation:
    return Citation(
        source_id=source.id,
        title=source.title,
        url=source.url,
        excerpt=source.excerpt,
        supports=[source.course_code],
    )


class GraphRepository(ABC):
    @abstractmethod
    def health(self) -> bool: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def search_courses(
        self, query: str, department: str | None = None, level: int | None = None, limit: int = 8
    ) -> list[Course]: ...

    @abstractmethod
    def get_course(self, code: str) -> Course | None: ...

    @abstractmethod
    def get_source(self, source_id: str) -> Source | None: ...

    @abstractmethod
    def citations_for(self, course_codes: Iterable[str]) -> list[Citation]: ...

    @abstractmethod
    def check_prerequisites(self, course_code: str, completed_courses: Iterable[str]) -> dict[str, Any]: ...

    @abstractmethod
    def learning_path(self, course_code: str, completed_courses: Iterable[str]) -> dict[str, Any]: ...

    @abstractmethod
    def graph_query(self, query_id: str, params: dict[str, Any]) -> dict[str, Any]: ...


class InMemoryGraphRepository(GraphRepository):
    """Deterministic adapter used by tests, evaluation, and optional offline demos."""

    def __init__(self) -> None:
        self._courses = {course.code: course for course in courses()}
        self._sources = {source.id: source for source in sources()}
        self._prerequisites = prerequisite_map()

    def health(self) -> bool:
        return True

    def close(self) -> None:
        return None

    @staticmethod
    def _trigrams(text: str) -> set[str]:
        clean = re.sub(r"[^a-z0-9]", "", text.lower())
        if len(clean) < 3:
            return {clean} if clean else set()
        return {clean[i : i + 3] for i in range(len(clean) - 2)}

    def search_courses(
        self, query: str, department: str | None = None, level: int | None = None, limit: int = 8
    ) -> list[Course]:
        """Hybrid retrieval combining lexical keyword scoring with dense subword semantic similarity via RRF."""
        tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        stop = {
            "a", "about", "an", "and", "course", "courses", "find", "for", "in", "me", "on",
            "show", "the", "what", "which", "with",
        }
        tokens -= stop
        query_trigrams = self._trigrams(query)

        candidates = [
            course for course in self._courses.values()
            if (not department or course.department == department.upper())
            and (not level or course.level == int(level))
        ]

        if not candidates:
            return []

        lexical_scores: list[tuple[float, Course]] = []
        for course in candidates:
            text = " ".join([course.code, course.title, course.description, *course.topics]).lower()
            words = set(re.findall(r"[a-z0-9]+", text))
            score = sum(3.0 if token in words else 1.0 for token in tokens if token in text)
            if course.code.lower() in query.lower():
                score += 30.0
            for topic in course.topics:
                if any(token in topic.lower() for token in tokens):
                    score += 4.0
            lexical_scores.append((score, course))
        lexical_scores.sort(key=lambda pair: (-pair[0], pair[1].level, pair[1].code))

        semantic_scores: list[tuple[float, Course]] = []
        for course in candidates:
            course_text = f"{course.code} {course.title} {course.description} {' '.join(course.topics)}"
            course_trigrams = self._trigrams(course_text)
            overlap = len(query_trigrams & course_trigrams)
            denom = (len(query_trigrams) ** 0.5 * len(course_trigrams) ** 0.5) or 1.0
            semantic_scores.append((overlap / denom, course))
        semantic_scores.sort(key=lambda pair: (-pair[0], pair[1].level, pair[1].code))

        max_lex = max((s for s, _ in lexical_scores), default=0.0)
        max_sem = max((s for s, _ in semantic_scores), default=0.0)
        if tokens and max_lex == 0.0 and max_sem < 0.12:
            return []

        rrf_scores: dict[str, float] = {course.code: 0.0 for course in candidates}
        for rank, (_, course) in enumerate(lexical_scores, start=1):
            rrf_scores[course.code] += 1.0 / (60.0 + rank)
        for rank, (_, course) in enumerate(semantic_scores, start=1):
            rrf_scores[course.code] += 1.0 / (60.0 + rank)

        for course in candidates:
            if course.code.lower() in query.lower():
                rrf_scores[course.code] += 1.0

        ranked = sorted(candidates, key=lambda course: (-rrf_scores[course.code], course.level, course.code))
        return ranked[: max(1, min(limit, 50))]

    def get_course(self, code: str) -> Course | None:
        return self._courses.get(code.upper().strip())

    def get_source(self, source_id: str) -> Source | None:
        return self._sources.get(source_id)

    def citations_for(self, course_codes: Iterable[str]) -> list[Citation]:
        result = []
        for code in _normalise_codes(course_codes):
            source = self._sources.get(f"catalog:{code}")
            if source:
                result.append(_citation(source))
        return result

    def _paths_from(self, course_code: str) -> list[list[str]]:
        code = course_code.upper().strip()
        if code not in self._courses:
            return []
        paths: list[list[str]] = []

        def walk(current: str, path: list[str]) -> None:
            required = self._prerequisites.get(current, [])
            if not required:
                paths.append(path)
            for prereq in required:
                next_path = [*path, prereq]
                walk(prereq, next_path)

        walk(code, [code])
        return paths or [[code]]

    def check_prerequisites(self, course_code: str, completed_courses: Iterable[str]) -> dict[str, Any]:
        code = course_code.upper().strip()
        if code not in self._courses:
            raise ValueError(f"Unknown course code: {code}")
        completed = set(_normalise_codes(completed_courses))
        missing: set[str] = set()
        visited: set[str] = set()

        def visit(current: str) -> None:
            if current in visited or current in completed:
                return
            visited.add(current)
            for prereq in self._prerequisites.get(current, []):
                if prereq not in completed:
                    missing.add(prereq)
                    visit(prereq)

        visit(code)
        paths = self._paths_from(code)
        evidence = _normalise_codes(node for path in paths for node in path)
        return {
            "kind": "prerequisite_check",
            "course": code,
            "completed": sorted(completed),
            "eligible": not missing,
            "missing": sorted(missing, key=lambda item: (self._courses[item].level, item)),
            "evidence_course_codes": evidence,
            "citations": [item.model_dump() for item in self.citations_for(evidence)],
            "graph_paths": [
                GraphPath(nodes=path, relationships=["REQUIRES"] * (len(path) - 1), description="Prerequisite chain").model_dump()
                for path in paths
            ],
        }

    def learning_path(self, course_code: str, completed_courses: Iterable[str]) -> dict[str, Any]:
        code = course_code.upper().strip()
        if code not in self._courses:
            raise ValueError(f"Unknown course code: {code}")
        completed = set(_normalise_codes(completed_courses))
        ordered: list[str] = []
        visiting: set[str] = set()

        def visit(current: str) -> None:
            if current in completed or current in ordered:
                return
            if current in visiting:
                raise ValueError("Cycle detected in prerequisite graph")
            visiting.add(current)
            for prereq in self._prerequisites.get(current, []):
                visit(prereq)
            visiting.remove(current)
            ordered.append(current)

        visit(code)
        paths = self._paths_from(code)
        evidence = _normalise_codes(node for path in paths for node in path)
        return {
            "kind": "learning_path",
            "goal": code,
            "completed": sorted(completed),
            "recommended_order": ordered,
            "evidence_course_codes": evidence,
            "citations": [item.model_dump() for item in self.citations_for(evidence)],
            "graph_paths": [
                GraphPath(nodes=path, relationships=["REQUIRES"] * (len(path) - 1), description="Prerequisite chain").model_dump()
                for path in paths
            ],
        }

    def _shortest_path(self, start: str, end: str) -> list[str]:
        start, end = start.upper(), end.upper()
        if start not in self._courses or end not in self._courses:
            return []
        neighbours: dict[str, set[str]] = {code: set() for code in self._courses}
        for course, prereqs in self._prerequisites.items():
            for prereq in prereqs:
                neighbours[course].add(prereq)
                neighbours[prereq].add(course)
        queue: deque[list[str]] = deque([[start]])
        seen = {start}
        while queue:
            path = queue.popleft()
            if path[-1] == end:
                return path
            for item in sorted(neighbours[path[-1]] - seen):
                seen.add(item)
                queue.append([*path, item])
        return []

    def graph_query(self, query_id: str, params: dict[str, Any]) -> dict[str, Any]:
        _, safe = validated_query(query_id, params)
        records: list[dict[str, Any]] = []
        paths: list[GraphPath] = []
        evidence: list[str] = []
        if query_id == "course_details":
            course = self.get_course(safe["code"])
            if course:
                prereqs = self._prerequisites[course.code]
                records = [{**course.model_dump(), "prerequisites": prereqs}]
                evidence = [course.code, *prereqs]
                paths = [GraphPath(nodes=[course.code, prereq], relationships=["REQUIRES"]) for prereq in prereqs]
                if not paths:
                    paths = [GraphPath(nodes=[course.code], description="Course node")]
        elif query_id == "prerequisites":
            paths = [GraphPath(nodes=path, relationships=["REQUIRES"] * (len(path) - 1)) for path in self._paths_from(safe["code"])]
            records = [{"course": safe["code"], "path": path.nodes} for path in paths]
            evidence = [node for path in paths for node in path.nodes]
        elif query_id == "unlocks":
            start = safe["code"]
            for code in self._courses:
                for path in self._paths_from(code):
                    if start in path[1:]:
                        oriented = list(reversed(path[: path.index(start) + 1]))
                        records.append({"code": code, "title": self._courses[code].title, "path": oriented})
                        paths.append(GraphPath(nodes=oriented, relationships=["UNLOCKS"] * (len(oriented) - 1)))
                        evidence.extend(oriented)
                        break
            records.sort(key=lambda item: (len(item["path"]), item["code"]))
        elif query_id == "shortest_path":
            path = self._shortest_path(safe["from_code"], safe["to_code"])
            records = [{"from_code": safe["from_code"], "to_code": safe["to_code"], "path": path}]
            evidence = path or [safe["from_code"], safe["to_code"]]
            paths = (
                [GraphPath(nodes=path, relationships=["PREREQUISITE_CONNECTION"] * (len(path) - 1))]
                if path else [GraphPath(nodes=[code], description="Disconnected query endpoint") for code in evidence]
            )
        elif query_id == "courses_by_department":
            found = [
                course for course in self._courses.values()
                if course.department == safe["department"] and course.level >= safe["level_min"]
            ][: safe["limit"]]
            records = [{"code": item.code, "title": item.title, "level": item.level} for item in found]
            evidence = [item.code for item in found]
            paths = [GraphPath(nodes=[item.code], description="Matching course node") for item in found]
        elif query_id == "topic_courses":
            topic = str(safe["topic"]).lower()
            found = [course for course in self._courses.values() if topic in " ".join(course.topics).lower()][: safe["limit"]]
            records = [{"code": item.code, "title": item.title, "level": item.level} for item in found]
            evidence = [item.code for item in found]
            paths = [GraphPath(nodes=[item.code], description=f"Course tagged with {topic}") for item in found]
        elif query_id == "program_requirements":
            program = get_program(safe["program_code"])
            if program:
                records = [
                    {
                        "program_code": program.code,
                        "program_title": program.title,
                        "code": code,
                        "title": self._courses[code].title,
                        "credits": self._courses[code].credits,
                        "offered_terms": list(offering_terms(code)),
                    }
                    for code in program.required_courses
                ]
                evidence = list(program.required_courses)
                paths = [
                    GraphPath(nodes=[program.code, code], relationships=["REQUIRES_COURSE"], description="Program requirement")
                    for code in program.required_courses
                ]
        evidence = _normalise_codes(evidence)
        return {
            "kind": "graph_query",
            "query_id": query_id,
            "records": records,
            "evidence_course_codes": evidence,
            "citations": [item.model_dump() for item in self.citations_for(evidence)],
            "graph_paths": [item.model_dump() for item in paths],
        }


class Neo4jGraphRepository(GraphRepository):
    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def health(self) -> bool:
        self._driver.verify_connectivity()
        return True

    def close(self) -> None:
        self._driver.close()

    def ensure_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT course_code IF NOT EXISTS FOR (c:Course) REQUIRE c.code IS UNIQUE",
            "CREATE CONSTRAINT source_id IF NOT EXISTS FOR (s:Source) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT program_code IF NOT EXISTS FOR (p:Program) REQUIRE p.code IS UNIQUE",
            "CREATE FULLTEXT INDEX course_search IF NOT EXISTS FOR (c:Course) ON EACH [c.code, c.title, c.description, c.topics_text]",
        ]
        with self._driver.session() as session:
            for statement in statements:
                session.run(statement).consume()
            session.run("CALL db.awaitIndexes(60)").consume()

    def seed_catalog(self) -> None:
        self.ensure_schema()
        course_rows = []
        source_rows = []
        for item in courses():
            course_rows.append(
                {
                    **item.model_dump(),
                    "topics_text": " | ".join(item.topics),
                    "offered_terms": list(offering_terms(item.code)),
                }
            )
        for item in sources():
            source_rows.append(item.model_dump())
        edges = [
            {"course": course, "prerequisite": prereq}
            for course, prereqs in prerequisite_map().items()
            for prereq in prereqs
        ]
        with self._driver.session() as session:
            session.run(
                """
                UNWIND $rows AS row
                MERGE (c:Course {code: row.code})
                SET c.title=row.title, c.department=row.department, c.level=row.level,
                    c.credits=row.credits, c.description=row.description,
                    c.topics=row.topics, c.topics_text=row.topics_text, c.source_id=row.source_id,
                    c.offered_terms=row.offered_terms
                """,
                rows=course_rows,
            ).consume()
            session.run(
                """
                UNWIND $rows AS row
                MERGE (s:Source {id: row.id})
                SET s.title=row.title, s.url=row.url, s.excerpt=row.excerpt, s.course_code=row.course_code
                """,
                rows=source_rows,
            ).consume()
            session.run(
                """
                UNWIND $rows AS row
                MATCH (s:Source {id: row.id})
                OPTIONAL MATCH (c:Course {code: row.course_code})
                FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END | MERGE (c)-[:HAS_SOURCE]->(s))
                """,
                rows=source_rows,
            ).consume()
            session.run(
                """
                MERGE (catalog:Catalog {id:'catalog'})
                WITH catalog MATCH (source:Source {id:'catalog:overview'})
                MERGE (catalog)-[:HAS_SOURCE]->(source)
                """
            ).consume()
            session.run(
                """
                UNWIND $rows AS row
                MERGE (p:Program {code:row.code})
                SET p.title=row.title, p.description=row.description
                """,
                rows=program_rows(),
            ).consume()
            session.run("MATCH (:Program)-[r:REQUIRES_COURSE]->(:Course) DELETE r").consume()
            session.run(
                """
                UNWIND $rows AS row
                MATCH (p:Program {code:row.program_code}), (c:Course {code:row.course_code})
                MERGE (p)-[:REQUIRES_COURSE]->(c)
                """,
                rows=program_requirement_rows(),
            ).consume()
            session.run(
                """
                MATCH (p:Program), (s:Source)
                WHERE s.id = 'catalog:program:' + p.code
                MERGE (p)-[:HAS_SOURCE]->(s)
                """
            ).consume()
            session.run("MATCH (:Course)-[r:REQUIRES]->(:Course) DELETE r").consume()
            session.run(
                """
                UNWIND $rows AS row
                MATCH (c:Course {code: row.course}), (p:Course {code: row.prerequisite})
                MERGE (c)-[:REQUIRES]->(p)
                """,
                rows=edges,
            ).consume()

    @staticmethod
    def _course(data: dict[str, Any]) -> Course:
        return Course(
            code=data["code"], title=data["title"], department=data["department"],
            level=data["level"], credits=data["credits"], description=data["description"],
            topics=list(data.get("topics", [])), source_id=data["source_id"],
        )

    def search_courses(
        self, query: str, department: str | None = None, level: int | None = None, limit: int = 8
    ) -> list[Course]:
        tokens = re.findall(r"[A-Za-z0-9]+", query)
        search = " OR ".join(f"{token}*" for token in tokens) or "*"
        with self._driver.session() as session:
            rows = session.run(
                """
                CALL db.index.fulltext.queryNodes('course_search', $search, {limit: $candidate_limit})
                YIELD node, score
                WHERE ($department IS NULL OR node.department = $department)
                  AND ($level IS NULL OR node.level = $level)
                RETURN node ORDER BY score DESC, node.code LIMIT $limit
                """,
                search=search,
                candidate_limit=min(max(limit * 4, 20), 100),
                department=department.upper() if department else None,
                level=level,
                limit=max(1, min(limit, 50)),
            )
            return [self._course(dict(record["node"])) for record in rows]

    def get_course(self, code: str) -> Course | None:
        with self._driver.session() as session:
            record = session.run("MATCH (c:Course {code:$code}) RETURN c", code=code.upper().strip()).single()
            return self._course(dict(record["c"])) if record else None

    def get_source(self, source_id: str) -> Source | None:
        with self._driver.session() as session:
            record = session.run("MATCH (s:Source {id:$id}) RETURN s", id=source_id).single()
            return Source(**dict(record["s"])) if record else None

    def citations_for(self, course_codes: Iterable[str]) -> list[Citation]:
        codes = _normalise_codes(course_codes)
        if not codes:
            return []
        with self._driver.session() as session:
            rows = session.run(
                """
                UNWIND $codes AS code
                MATCH (c:Course {code:code})-[:HAS_SOURCE]->(s:Source)
                RETURN s ORDER BY code
                """,
                codes=codes,
            )
            return [_citation(Source(**dict(row["s"]))) for row in rows]

    def _prerequisite_paths(self, code: str) -> list[list[str]]:
        with self._driver.session() as session:
            rows = session.run(
                """
                MATCH (c:Course {code:$code})
                OPTIONAL MATCH p=(c)-[:REQUIRES*1..8]->(required:Course)
                WHERE required IS NULL OR NOT (required)-[:REQUIRES]->(:Course)
                RETURN CASE WHEN p IS NULL THEN [c.code] ELSE [n IN nodes(p) | n.code] END AS path
                ORDER BY size(path), path
                """,
                code=code,
            )
            return [list(row["path"]) for row in rows]

    def check_prerequisites(self, course_code: str, completed_courses: Iterable[str]) -> dict[str, Any]:
        code = course_code.upper().strip()
        if not self.get_course(code):
            raise ValueError(f"Unknown course code: {code}")
        completed = set(_normalise_codes(completed_courses))
        paths = self._prerequisite_paths(code)
        missing: set[str] = set()
        for path in paths:
            for node in path[1:]:
                if any(ancestor in completed for ancestor in path[1:path.index(node) + 1]):
                    break
                if node not in completed:
                    missing.add(node)
        evidence = _normalise_codes(node for path in paths for node in path)
        return {
            "kind": "prerequisite_check", "course": code, "completed": sorted(completed),
            "eligible": not missing, "missing": sorted(missing), "evidence_course_codes": evidence,
            "citations": [item.model_dump() for item in self.citations_for(evidence)],
            "graph_paths": [GraphPath(nodes=path, relationships=["REQUIRES"] * (len(path) - 1), description="Prerequisite chain").model_dump() for path in paths],
        }

    def learning_path(self, course_code: str, completed_courses: Iterable[str]) -> dict[str, Any]:
        code = course_code.upper().strip()
        if not self.get_course(code):
            raise ValueError(f"Unknown course code: {code}")
        completed = set(_normalise_codes(completed_courses))
        paths = self._prerequisite_paths(code)
        prereqs: dict[str, set[str]] = {}
        for path in paths:
            for current, required in zip(path, path[1:]):
                prereqs.setdefault(current, set()).add(required)
        ordered: list[str] = []

        def visit(current: str) -> None:
            if current in completed or current in ordered:
                return
            for required in sorted(prereqs.get(current, set())):
                visit(required)
            ordered.append(current)

        visit(code)
        evidence = _normalise_codes(node for path in paths for node in path)
        return {
            "kind": "learning_path", "goal": code, "completed": sorted(completed),
            "recommended_order": ordered, "evidence_course_codes": evidence,
            "citations": [item.model_dump() for item in self.citations_for(evidence)],
            "graph_paths": [GraphPath(nodes=path, relationships=["REQUIRES"] * (len(path) - 1), description="Prerequisite chain").model_dump() for path in paths],
        }

    def graph_query(self, query_id: str, params: dict[str, Any]) -> dict[str, Any]:
        spec, safe = validated_query(query_id, params)
        with self._driver.session() as session:
            records = [dict(record) for record in session.run(spec.cypher, **safe)]
        raw_paths = [record.get("path") for record in records if record.get("path")]
        evidence = _normalise_codes(
            value
            for record in records
            for key, item in record.items()
            for value in (item if isinstance(item, list) else [item])
            if isinstance(value, str) and re.fullmatch(r"[A-Z]{2,5}\d{3}", value)
        )
        paths = [
            GraphPath(nodes=list(path), relationships=["PREREQUISITE_CONNECTION"] * (len(path) - 1)).model_dump()
            for path in raw_paths
        ]
        if not paths:
            paths = [GraphPath(nodes=[code], description="Matching course node").model_dump() for code in evidence]
        return {
            "kind": "graph_query", "query_id": query_id, "records": records,
            "evidence_course_codes": evidence,
            "citations": [item.model_dump() for item in self.citations_for(evidence)],
            "graph_paths": paths,
        }

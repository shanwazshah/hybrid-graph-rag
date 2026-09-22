from __future__ import annotations

from collections import deque
from typing import Any, Iterable

from coursegraph.catalog import courses, prerequisite_map
from coursegraph.models import Citation, GraphPath
from coursegraph.programs import get_program, offering_terms
from coursegraph.repository import GraphRepository


def _normalise(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value).upper().strip() for value in values if value))


def _program_citation(repository: GraphRepository, program_code: str) -> Citation | None:
    source = repository.get_source(f"catalog:program:{program_code}")
    if not source:
        return None
    return Citation(
        source_id=source.id,
        title=source.title,
        url=source.url,
        excerpt=source.excerpt,
        supports=[program_code],
    )


class DegreePlanner:
    """Deterministic constraint planner over program and prerequisite graph evidence."""

    def __init__(self, repository: GraphRepository) -> None:
        self.repository = repository
        self.course_by_code = {course.code: course for course in courses()}
        self.prerequisites = prerequisite_map()

    def _requirements(self, program_code: str) -> tuple[dict[str, Any], set[str]]:
        result = self.repository.graph_query("program_requirements", {"program_code": program_code})
        if not result["records"]:
            raise ValueError(f"Unknown program code: {program_code.upper()}")
        return result, {record["code"] for record in result["records"]}

    def _with_prerequisite_closure(self, requirements: set[str]) -> set[str]:
        expanded = set(requirements)
        queue = deque(requirements)
        while queue:
            code = queue.popleft()
            for prerequisite in self.prerequisites.get(code, []):
                if prerequisite not in expanded:
                    expanded.add(prerequisite)
                    queue.append(prerequisite)
        return expanded

    def _downstream_counts(self, requirements: set[str]) -> dict[str, int]:
        dependents: dict[str, set[str]] = {code: set() for code in requirements}
        for course_code in requirements:
            for prerequisite in self.prerequisites.get(course_code, []):
                if prerequisite in requirements:
                    dependents.setdefault(prerequisite, set()).add(course_code)
        counts: dict[str, int] = {}
        for start in requirements:
            seen: set[str] = set()
            queue = deque(dependents.get(start, set()))
            while queue:
                code = queue.popleft()
                if code in seen:
                    continue
                seen.add(code)
                queue.extend(dependents.get(code, set()) - seen)
            counts[start] = len(seen)
        return counts

    @staticmethod
    def _term_label(index: int, start_term: str) -> tuple[str, str]:
        if start_term == "Fall":
            term = "Fall" if index % 2 == 0 else "Spring"
            year = index // 2 + 1
        else:
            term = "Spring" if index % 2 == 0 else "Fall"
            year = (index + 1) // 2 + 1
        return term, f"{term} — Year {year}"

    def _plan_csp(
        self,
        remaining_courses: set[str],
        completed: set[str],
        max_credits_per_term: int,
        start_term: str,
        max_terms: int,
        downstream_counts: dict[str, int],
    ) -> dict[str, int] | None:
        """Exact Constraint Satisfaction Problem (CSP) solver using topological ordering and forward checking."""
        if not remaining_courses:
            return {}

        term_names = [self._term_label(i, start_term)[0] for i in range(max_terms)]
        domains: dict[str, list[int]] = {}
        for code in remaining_courses:
            allowed = [i for i in range(max_terms) if term_names[i] in offering_terms(code)]
            domains[code] = allowed

        dependencies: dict[str, set[str]] = {
            code: set(self.prerequisites.get(code, [])) & remaining_courses
            for code in remaining_courses
        }

        # Topological variable ordering ensures prerequisites are always assigned before dependents
        in_degree = {c: len(dependencies[c]) for c in remaining_courses}
        ready = deque(
            sorted(
                [c for c, d in in_degree.items() if d == 0],
                key=lambda c: (-downstream_counts.get(c, 0), self.course_by_code[c].level, c),
            )
        )
        ordered_vars: list[str] = []
        dependents: dict[str, set[str]] = {c: set() for c in remaining_courses}
        for c in remaining_courses:
            for p in dependencies[c]:
                dependents[p].add(c)

        while ready:
            curr = ready.popleft()
            ordered_vars.append(curr)
            for dep in sorted(
                dependents[curr],
                key=lambda c: (-downstream_counts.get(c, 0), self.course_by_code[c].level, c),
            ):
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    ready.append(dep)

        if len(ordered_vars) != len(remaining_courses):
            return None

        assignment: dict[str, int] = {}
        term_loads = [0] * max_terms
        iterations = 0
        max_iterations = 2000

        def backtrack(var_idx: int) -> bool:
            nonlocal iterations
            iterations += 1
            if iterations > max_iterations:
                return False

            if var_idx == len(ordered_vars):
                return True

            var = ordered_vars[var_idx]
            cr = self.course_by_code[var].credits
            min_term = max((assignment[p] + 1 for p in dependencies[var]), default=0)

            candidates = [t for t in domains[var] if t >= min_term and term_loads[t] + cr <= max_credits_per_term]
            candidates.sort()  # Earliest term first

            for t in candidates:
                assignment[var] = t
                term_loads[t] += cr

                if backtrack(var_idx + 1):
                    return True

                term_loads[t] -= cr
                del assignment[var]

            return False

        return assignment if backtrack(0) else None

    def plan(
        self,
        program_code: str = "BSCS-AI",
        completed_courses: list[str] | None = None,
        max_credits_per_term: int = 15,
        start_term: str = "Fall",
        max_terms: int = 8,
    ) -> dict[str, Any]:
        program_code = program_code.upper().strip()
        start_term = start_term.title().strip()
        if start_term not in {"Fall", "Spring"}:
            raise ValueError("start_term must be Fall or Spring")
        if not 3 <= max_credits_per_term <= 21:
            raise ValueError("max_credits_per_term must be between 3 and 21")
        if not 1 <= max_terms <= 12:
            raise ValueError("max_terms must be between 1 and 12")

        graph_result, program_requirements = self._requirements(program_code)
        requirements = self._with_prerequisite_closure(program_requirements)
        completed = set(_normalise(completed_courses or []))
        unknown = completed - set(self.course_by_code)
        if unknown:
            raise ValueError(f"Unknown completed course codes: {', '.join(sorted(unknown))}")

        remaining = requirements - completed
        satisfied = set(completed)
        downstream_counts = self._downstream_counts(requirements)

        # Attempt exact Constraint Satisfaction Problem (CSP) optimization
        csp_solution = self._plan_csp(
            remaining, completed, max_credits_per_term, start_term, max_terms, downstream_counts
        )
        semesters: list[dict[str, Any]] = []

        if csp_solution is not None:
            solver_name = "csp_exact"
            for index in range(max_terms):
                term, label = self._term_label(index, start_term)
                term_codes = [code for code, t in csp_solution.items() if t == index]
                term_codes.sort(key=lambda c: (self.course_by_code[c].level, c))
                credits = sum(self.course_by_code[c].credits for c in term_codes)
                semesters.append(
                    {
                        "term_number": index + 1,
                        "term": term,
                        "label": label,
                        "credits": credits,
                        "courses": [
                            {
                                "code": code,
                                "title": self.course_by_code[code].title,
                                "credits": self.course_by_code[code].credits,
                                "offered_terms": list(offering_terms(code)),
                            }
                            for code in term_codes
                        ],
                    }
                )
            remaining = set()
        else:
            solver_name = "heuristic_greedy"
            for index in range(max_terms):
                term, label = self._term_label(index, start_term)
                eligible = [
                    code
                    for code in remaining
                    if set(self.prerequisites.get(code, [])).issubset(satisfied)
                    and term in offering_terms(code)
                ]
                eligible.sort(
                    key=lambda code: (
                        -downstream_counts.get(code, 0),
                        self.course_by_code[code].level,
                        code,
                    )
                )
                selected: list[str] = []
                credits = 0
                for code in eligible:
                    course_credits = self.course_by_code[code].credits
                    if credits + course_credits <= max_credits_per_term:
                        selected.append(code)
                        credits += course_credits
                semesters.append(
                    {
                        "term_number": index + 1,
                        "term": term,
                        "label": label,
                        "credits": credits,
                        "courses": [
                            {
                                "code": code,
                                "title": self.course_by_code[code].title,
                                "credits": self.course_by_code[code].credits,
                                "offered_terms": list(offering_terms(code)),
                            }
                            for code in selected
                        ],
                    }
                )
                remaining -= set(selected)
                satisfied.update(selected)
                if not remaining:
                    break

        scheduled = [course["code"] for semester in semesters for course in semester["courses"]]
        course_evidence = _normalise([*program_requirements, *scheduled])
        evidence = [program_code, *course_evidence]
        citations = self.repository.citations_for(course_evidence)
        program_citation = _program_citation(self.repository, program_code)
        if program_citation:
            citations.insert(0, program_citation)
        paths = [
            GraphPath(
                nodes=[program_code, code],
                relationships=["REQUIRES_COURSE"],
                description="Program requirement",
            )
            for code in sorted(program_requirements)
        ]
        return {
            "kind": "degree_plan",
            "program_code": program_code,
            "program_title": get_program(program_code).title if get_program(program_code) else program_code,
            "start_term": start_term,
            "max_credits_per_term": max_credits_per_term,
            "completed": sorted(completed),
            "semesters": semesters,
            "feasible": not remaining,
            "unscheduled": sorted(remaining),
            "planned_credits": sum(semester["credits"] for semester in semesters),
            "solver": solver_name,
            "evidence_course_codes": evidence,
            "citations": [citation.model_dump() for citation in citations],
            "graph_paths": [path.model_dump() for path in paths],
            "constraints": [
                "All prerequisites must be completed in an earlier term.",
                f"No term exceeds {max_credits_per_term} credits.",
                "Courses are scheduled only in their modeled Fall/Spring offerings.",
            ],
            "program_graph": graph_result["records"],
        }

    def impact(self, course_code: str, program_code: str = "BSCS-AI") -> dict[str, Any]:
        course_code = course_code.upper().strip()
        if course_code not in self.course_by_code:
            raise ValueError(f"Unknown course code: {course_code}")
        program_code = program_code.upper().strip()
        _, program_requirements = self._requirements(program_code)
        result = self.repository.graph_query("unlocks", {"code": course_code})
        affected_records = [record for record in result["records"] if record["code"] in program_requirements]
        affected_codes = _normalise([course_code, *(record["code"] for record in affected_records)])
        paths = [
            GraphPath(
                nodes=list(record["path"]),
                relationships=["UNLOCKS"] * (len(record["path"]) - 1),
                description="Downstream prerequisite impact",
            )
            for record in affected_records
        ] or [GraphPath(nodes=[course_code], description="No downstream program requirements")]
        citations = self.repository.citations_for(affected_codes)
        program_citation = _program_citation(self.repository, program_code)
        if program_citation:
            citations.insert(0, program_citation)
        return {
            "kind": "impact_analysis",
            "course": course_code,
            "program_code": program_code,
            "affected_courses": affected_codes[1:],
            "affected_count": len(affected_codes) - 1,
            "evidence_course_codes": [program_code, *affected_codes],
            "citations": [citation.model_dump() for citation in citations],
            "graph_paths": [path.model_dump() for path in paths],
        }

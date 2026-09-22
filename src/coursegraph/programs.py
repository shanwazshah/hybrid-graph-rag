from dataclasses import dataclass


@dataclass(frozen=True)
class ProgramSeed:
    code: str
    title: str
    description: str
    required_courses: tuple[str, ...]


PROGRAMS: tuple[ProgramSeed, ...] = (
    ProgramSeed(
        code="BSCS-AI",
        title="Computer Science — Artificial Intelligence Specialization",
        description=(
            "A technical program pathway covering computer science foundations, systems, data, "
            "machine learning, responsible AI, and a software capstone. General-education "
            "requirements are outside this demonstration catalog."
        ),
        required_courses=(
            "CS101", "MATH101", "MATH201", "MATH210", "CS102", "MATH102", "DATA101",
            "CS201", "CS202", "CS204", "MATH220", "CS203", "CS205", "DATA201", "CS250",
            "CS301", "CS302", "AI101", "CS303", "CS320", "AI201", "CS340", "AI210",
            "AI301", "AI330", "AI302", "AI303", "CS410",
        ),
    ),
)


_ADVANCED_OFFERINGS: dict[str, tuple[str, ...]] = {
    "CS301": ("Fall",),
    "CS302": ("Fall",),
    "AI101": ("Fall",),
    "CS303": ("Spring",),
    "CS320": ("Spring",),
    "AI201": ("Spring",),
    "CS340": ("Spring",),
    "AI210": ("Fall",),
    "AI301": ("Fall",),
    "AI330": ("Fall",),
    "AI302": ("Spring",),
    "AI303": ("Spring",),
    "CS410": ("Spring",),
}


def get_program(code: str) -> ProgramSeed | None:
    normalised = code.upper().strip()
    return next((program for program in PROGRAMS if program.code == normalised), None)


def offering_terms(course_code: str) -> tuple[str, ...]:
    return _ADVANCED_OFFERINGS.get(course_code.upper().strip(), ("Fall", "Spring"))


def program_rows() -> list[dict[str, object]]:
    return [
        {
            "code": program.code,
            "title": program.title,
            "description": program.description,
            "required_courses": list(program.required_courses),
        }
        for program in PROGRAMS
    ]


def program_requirement_rows() -> list[dict[str, str]]:
    return [
        {"program_code": program.code, "course_code": course_code}
        for program in PROGRAMS
        for course_code in program.required_courses
    ]


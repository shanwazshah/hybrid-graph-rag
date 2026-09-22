from dataclasses import dataclass

from coursegraph.models import Course, Source
from coursegraph.programs import PROGRAMS


@dataclass(frozen=True)
class CourseSeed:
    code: str
    title: str
    department: str
    level: int
    description: str
    topics: tuple[str, ...]
    prerequisites: tuple[str, ...] = ()
    credits: int = 3

    def as_course(self) -> Course:
        return Course(
            code=self.code,
            title=self.title,
            department=self.department,
            level=self.level,
            credits=self.credits,
            description=self.description,
            topics=list(self.topics),
            source_id=f"catalog:{self.code}",
        )

    def as_source(self) -> Source:
        return Source(
            id=f"catalog:{self.code}",
            title=f"University Catalog — {self.code}: {self.title}",
            url=f"https://catalog.example.edu/courses/{self.code.lower()}",
            excerpt=(
                f"{self.code} {self.title}. {self.credits} credits. {self.description} "
                f"Prerequisites: {', '.join(self.prerequisites) if self.prerequisites else 'None'}."
            ),
            course_code=self.code,
        )


def _c(code: str, title: str, dept: str, level: int, description: str, topics: str, prereqs: str = "") -> CourseSeed:
    return CourseSeed(
        code=code,
        title=title,
        department=dept,
        level=level,
        description=description,
        topics=tuple(topic.strip() for topic in topics.split(",")),
        prerequisites=tuple(item for item in prereqs.split() if item),
    )


COURSE_CATALOG: tuple[CourseSeed, ...] = (
    _c("MATH101", "Calculus I", "MATH", 100, "Limits, derivatives, integrals, and mathematical modeling.", "calculus,derivatives,integrals"),
    _c("MATH102", "Calculus II", "MATH", 100, "Integration techniques, sequences, series, and parametric curves.", "calculus,series,integration", "MATH101"),
    _c("MATH201", "Linear Algebra", "MATH", 200, "Vectors, matrices, linear transformations, eigenvalues, and applications.", "linear algebra,matrices,eigenvalues"),
    _c("MATH210", "Discrete Mathematics", "MATH", 200, "Logic, proof, combinatorics, relations, and discrete structures.", "logic,proofs,combinatorics"),
    _c("MATH220", "Probability and Statistics", "MATH", 200, "Probability models, estimation, hypothesis testing, and regression.", "probability,statistics,regression", "MATH102"),
    _c("MATH301", "Numerical Methods", "MATH", 300, "Stable numerical algorithms for scientific computing.", "numerical computing,optimization,approximation", "MATH102 MATH201"),
    _c("MATH310", "Graph Theory", "MATH", 300, "Graphs, trees, connectivity, matchings, and network applications.", "graphs,networks,combinatorics", "MATH210"),
    _c("MATH320", "Mathematical Optimization", "MATH", 300, "Convex optimization, duality, and constrained methods.", "optimization,convexity,duality", "MATH102 MATH201"),
    _c("CS101", "Introduction to Programming", "CS", 100, "Problem solving with Python, control flow, functions, and testing.", "python,programming,testing"),
    _c("CS102", "Data Structures", "CS", 100, "Lists, trees, hash tables, graphs, and complexity analysis.", "data structures,algorithms,complexity", "CS101"),
    _c("CS201", "Design and Analysis of Algorithms", "CS", 200, "Algorithm design paradigms, correctness, and asymptotic analysis.", "algorithms,dynamic programming,complexity", "CS102 MATH210"),
    _c("CS202", "Computer Architecture", "CS", 200, "Instruction sets, memory hierarchy, processors, and digital systems.", "architecture,processors,memory", "CS102"),
    _c("CS203", "Systems Programming", "CS", 200, "C programming, processes, memory, files, and systems interfaces.", "systems,c,processes", "CS102 CS202"),
    _c("CS204", "Database Systems", "CS", 200, "Relational modeling, SQL, transactions, indexing, and query planning.", "databases,sql,indexing", "CS102"),
    _c("CS205", "Software Engineering", "CS", 200, "Team software delivery, architecture, testing, and continuous integration.", "software engineering,testing,architecture", "CS102"),
    _c("CS210", "Theory of Computation", "CS", 200, "Automata, computability, formal languages, and complexity.", "automata,formal languages,complexity", "CS201"),
    _c("CS220", "Web Application Development", "CS", 200, "Accessible full-stack web applications and HTTP APIs.", "web,api,javascript", "CS102"),
    _c("CS230", "Human-Computer Interaction", "CS", 200, "User-centered design, prototyping, and usability evaluation.", "hci,ux,prototyping", "CS101"),
    _c("CS250", "Computing, Ethics, and Society", "CS", 200, "Ethical reasoning about privacy, fairness, platforms, and automation.", "ethics,privacy,fairness"),
    _c("CS301", "Operating Systems", "CS", 300, "Processes, threads, scheduling, memory, storage, and isolation.", "operating systems,concurrency,memory", "CS203"),
    _c("CS302", "Computer Networks", "CS", 300, "Layered network protocols, routing, congestion, and network applications.", "networks,tcp,protocols", "CS203"),
    _c("CS303", "Distributed Systems", "CS", 300, "Fault tolerance, replication, consensus, and distributed data.", "distributed systems,consensus,replication", "CS301 CS302"),
    _c("CS304", "Compiler Construction", "CS", 300, "Parsing, semantic analysis, optimization, and code generation.", "compilers,parsing,code generation", "CS201 CS203"),
    _c("CS305", "Cybersecurity Engineering", "CS", 300, "Threat modeling, cryptography, secure design, and incident response.", "security,cryptography,threat modeling", "CS302"),
    _c("CS306", "Parallel Computing", "CS", 300, "Shared-memory, distributed, and accelerator programming models.", "parallel computing,gpu,concurrency", "CS201 CS301"),
    _c("CS310", "Programming Languages", "CS", 300, "Language semantics, type systems, interpreters, and functional programming.", "programming languages,types,semantics", "CS201"),
    _c("CS320", "Information Retrieval", "CS", 300, "Indexing, ranking, search evaluation, and knowledge retrieval.", "information retrieval,search,ranking", "CS201 CS204 MATH220"),
    _c("CS330", "Data Visualization", "CS", 300, "Visual encodings, interaction, perception, and explanatory graphics.", "visualization,graphics,perception", "CS102 MATH201"),
    _c("CS340", "Cloud Computing", "CS", 300, "Cloud architecture, containers, orchestration, and resilient services.", "cloud,containers,kubernetes", "CS204 CS302"),
    _c("CS350", "Mobile Application Engineering", "CS", 300, "Native and cross-platform mobile product engineering.", "mobile,applications,product", "CS205"),
    _c("CS360", "Quantum Computing Foundations", "CS", 300, "Qubits, quantum circuits, algorithms, and error concepts.", "quantum computing,algorithms,physics", "MATH201 MATH220"),
    _c("CS401", "Advanced Algorithms", "CS", 400, "Randomized, approximation, streaming, and graph algorithms.", "advanced algorithms,graphs,randomization", "CS201 MATH310"),
    _c("CS410", "Software Systems Capstone", "CS", 400, "Teams design, deliver, and evaluate a production software system.", "capstone,software engineering,delivery", "CS205 CS301 CS302"),
    _c("DATA101", "Introduction to Data Science", "DATA", 100, "Data analysis with Python, notebooks, visualization, and reproducibility.", "data science,python,analysis", "CS101 MATH101"),
    _c("DATA201", "Data Wrangling and Management", "DATA", 200, "Reliable ingestion, cleaning, transformation, and data quality.", "data wrangling,etl,quality", "DATA101 CS204"),
    _c("DATA202", "Statistical Modeling for Data Science", "DATA", 200, "Regression, generalized models, resampling, and uncertainty.", "statistics,modeling,inference", "MATH220"),
    _c("DATA210", "Communicating with Data", "DATA", 200, "Visualization, narrative, dashboards, and responsible communication.", "visualization,storytelling,dashboards", "DATA101 CS230"),
    _c("DATA220", "Big Data Systems", "DATA", 200, "Distributed storage, batch and stream processing, and data platforms.", "big data,streaming,distributed systems", "DATA201 CS301"),
    _c("DATA301", "Data Mining", "DATA", 300, "Pattern discovery, clustering, classification, and evaluation.", "data mining,clustering,classification", "DATA201 DATA202 CS201"),
    _c("DATA302", "Analytics Engineering", "DATA", 300, "Tested transformations, semantic layers, orchestration, and observability.", "analytics engineering,dbt,orchestration", "DATA201 CS205"),
    _c("DATA310", "Time Series Analysis", "DATA", 300, "Forecasting, state-space models, seasonality, and anomalies.", "time series,forecasting,anomalies", "DATA202"),
    _c("DATA320", "Causal Inference", "DATA", 300, "Experiments, causal graphs, matching, and treatment effects.", "causal inference,experiments,graphs", "DATA202 MATH320"),
    _c("DATA330", "Data Privacy and Governance", "DATA", 300, "Privacy engineering, governance, lineage, and data policy.", "privacy,governance,lineage", "DATA201 CS250"),
    _c("DATA401", "Data Science Capstone", "DATA", 400, "End-to-end data product delivery with stakeholder evaluation.", "capstone,data product,evaluation", "DATA301 DATA302"),
    _c("AI101", "Introduction to Artificial Intelligence", "AI", 100, "Search, planning, reasoning, and intelligent agents.", "artificial intelligence,search,planning", "CS201 MATH201"),
    _c("AI201", "Machine Learning", "AI", 200, "Supervised and unsupervised learning, generalization, and evaluation.", "machine learning,classification,clustering", "AI101 MATH220"),
    _c("AI202", "Knowledge Representation and Reasoning", "AI", 200, "Logic, ontologies, knowledge graphs, and automated reasoning.", "knowledge graphs,logic,reasoning", "AI101 MATH210"),
    _c("AI210", "Natural Language Processing", "AI", 200, "Text representations, language models, parsing, and evaluation.", "nlp,language models,text", "AI201 CS320"),
    _c("AI220", "Computer Vision", "AI", 200, "Image formation, recognition, detection, and visual learning.", "computer vision,images,deep learning", "AI201 MATH201"),
    _c("AI230", "Robotics", "AI", 200, "Sensing, localization, motion planning, and robot control.", "robotics,planning,control", "AI101 CS202"),
    _c("AI240", "Reinforcement Learning", "AI", 200, "Sequential decision making, value methods, and policy optimization.", "reinforcement learning,control,optimization", "AI201 MATH320"),
    _c("AI301", "Deep Learning", "AI", 300, "Neural networks, representation learning, optimization, and deployment.", "deep learning,neural networks,optimization", "AI201"),
    _c("AI302", "Generative AI Systems", "AI", 300, "Foundation models, retrieval augmentation, evaluation, and safety.", "generative ai,rag,foundation models", "AI210 AI301"),
    _c("AI303", "Responsible AI", "AI", 300, "Fairness, transparency, robustness, governance, and human oversight.", "responsible ai,fairness,governance", "AI201 CS250"),
    _c("AI310", "Graph Machine Learning", "AI", 300, "Representation learning and prediction on graph-structured data.", "graph neural networks,graphs,representation learning", "AI201 MATH310"),
    _c("AI320", "Recommender Systems", "AI", 300, "Ranking, collaborative filtering, feedback loops, and evaluation.", "recommenders,ranking,personalization", "AI201 CS320"),
    _c("AI330", "Machine Learning Operations", "AI", 300, "Reproducible training, deployment, monitoring, and ML platforms.", "mlops,monitoring,deployment", "AI201 CS340"),
    _c("AI401", "AI Research Seminar", "AI", 400, "Critical reading and replication of current AI research.", "research,replication,ai", "AI301 AI303"),
    _c("HCI101", "Design Thinking", "HCI", 100, "Human-centered problem framing, ideation, prototyping, and critique.", "design thinking,prototyping,innovation"),
    _c("HCI201", "Interaction Design", "HCI", 200, "Interaction patterns, prototyping, and design systems.", "interaction design,prototyping,design systems", "HCI101 CS230"),
    _c("HCI202", "User Research Methods", "HCI", 200, "Interviews, field studies, surveys, and qualitative synthesis.", "user research,interviews,qualitative", "HCI101"),
    _c("HCI210", "Accessible Computing", "HCI", 200, "Inclusive design, assistive technology, and accessibility testing.", "accessibility,inclusive design,testing", "CS230"),
    _c("HCI301", "UX Engineering", "HCI", 300, "Production front ends built from research-backed interaction designs.", "ux engineering,frontend,design systems", "HCI201 CS220"),
    _c("HCI302", "Human-AI Interaction", "HCI", 300, "Design and evaluation of explainable, collaborative AI systems.", "human ai interaction,explainability,evaluation", "HCI201 AI101"),
    _c("INFS101", "Information Systems Foundations", "INFS", 100, "Organizations, processes, enterprise systems, and data.", "information systems,organizations,processes"),
    _c("INFS201", "Digital Product Management", "INFS", 200, "Product discovery, prioritization, metrics, and roadmaps.", "product management,metrics,roadmaps", "INFS101 HCI101"),
    _c("INFS210", "Technology Entrepreneurship", "INFS", 200, "Opportunity discovery, business models, experiments, and pitching.", "entrepreneurship,business models,experiments", "HCI101"),
    _c("INFS301", "Digital Platforms and Ecosystems", "INFS", 300, "Platform strategy, APIs, governance, and network effects.", "platforms,apis,network effects", "CS204 INFS201"),
)


def courses() -> list[Course]:
    return [item.as_course() for item in COURSE_CATALOG]


def sources() -> list[Source]:
    return [
        *[item.as_source() for item in COURSE_CATALOG],
        *[
            Source(
                id=f"catalog:program:{program.code}",
                title=f"University Catalog — {program.title}",
                url=f"https://catalog.example.edu/programs/{program.code.lower()}",
                excerpt=(
                    f"{program.title}. Technical pathway with {len(program.required_courses)} required "
                    "courses; general-education requirements are outside this demonstration catalog."
                ),
                course_code=program.code,
            )
            for program in PROGRAMS
        ],
        Source(
            id="catalog:overview",
            title="University Course Catalog Overview",
            url="https://catalog.example.edu/courses",
            excerpt="The CourseGraph demonstration catalog contains 69 courses across six departments.",
            course_code="CATALOG",
        ),
    ]


def prerequisite_map() -> dict[str, list[str]]:
    return {item.code: list(item.prerequisites) for item in COURSE_CATALOG}

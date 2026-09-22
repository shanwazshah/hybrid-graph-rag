from __future__ import annotations

import time

from coursegraph.catalog import COURSE_CATALOG
from coursegraph.config import get_settings
from coursegraph.repository import Neo4jGraphRepository


def main() -> None:
    settings = get_settings()
    repository = Neo4jGraphRepository(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    try:
        last_error: Exception | None = None
        for attempt in range(1, 31):
            try:
                repository.health()
                repository.seed_catalog()
                print(f"Seeded {len(COURSE_CATALOG)} courses into Neo4j.")
                return
            except Exception as exc:
                last_error = exc
                if attempt == 30:
                    break
                time.sleep(2)
        raise RuntimeError(f"Neo4j did not become ready: {last_error}")
    finally:
        repository.close()


if __name__ == "__main__":
    main()


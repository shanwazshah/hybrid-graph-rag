from coursegraph.catalog import COURSE_CATALOG, prerequisite_map


def test_catalog_has_portfolio_scale_and_unique_codes() -> None:
    codes = [item.code for item in COURSE_CATALOG]
    assert 50 <= len(codes) <= 100
    assert len(codes) == len(set(codes))


def test_every_prerequisite_points_to_a_known_course() -> None:
    known = {item.code for item in COURSE_CATALOG}
    assert all(prerequisite in known for values in prerequisite_map().values() for prerequisite in values)


def test_catalog_covers_multiple_disciplines() -> None:
    departments = {item.department for item in COURSE_CATALOG}
    assert {"CS", "AI", "DATA", "MATH", "HCI", "INFS"}.issubset(departments)


import pytest
from backend.queries import (
    build_project_search,
    build_suggest,
    build_facets,
    build_page,
    build_search_after,
    parse_sort,
    parse_cursor,
    to_indian_date,
    validate_size,
    validate_page,
    extract_sections,
    compute_casing_collisions,
    CORE_FIELDS,
    DISABLED_OBJECTS,
    HIGHLIGHT_PRE,
    HIGHLIGHT_POST,
)
from backend.schemas import AppError


def test_validate_size():
    assert validate_size(10) == 10
    assert validate_size(100) == 100
    with pytest.raises(AppError) as exc:
        validate_size(0)
    assert exc.value.code == "invalid_request"
    with pytest.raises(AppError):
        validate_size(101)


def test_validate_page():
    assert validate_page(1, 20) == 0
    assert validate_page(2, 20) == 20
    assert validate_page(500, 20) == 9980
    with pytest.raises(AppError) as exc:
        validate_page(501, 20)  # 501 * 20 = 10020 > 10000
    assert "10000" in exc.value.message


def test_to_indian_date():
    assert to_indian_date("2024-05-15") == "15-05-2024"
    assert to_indian_date("15-05-2024") == "15-05-2024"
    assert to_indian_date("15/05/2024") == "15-05-2024"
    with pytest.raises(AppError):
        to_indian_date("invalid-date")


def test_parse_sort():
    assert parse_sort(None) == [{"projectId": "asc"}]
    assert parse_sort("projectId:desc") == [{"projectId": "desc"}]
    assert parse_sort("project_name.keyword:asc") == [
        {"project_name.keyword": "asc"},
        {"projectId": "asc"},
    ]
    assert parse_sort("start_date:desc") == [
        {"start_date": "desc"},
        {"projectId": "desc"},
    ]
    with pytest.raises(AppError):
        parse_sort("unsupported_field:asc")
    with pytest.raises(AppError):
        parse_sort("district:sideways")


def test_parse_cursor():
    assert parse_cursor(None) == []
    assert parse_cursor("") == []
    assert parse_cursor("[58]") == [58]
    assert parse_cursor("[58, 20277]") == [58, 20277]
    with pytest.raises(AppError):
        parse_cursor("58")  # not a list
    with pytest.raises(AppError):
        parse_cursor("[]")  # empty list
    with pytest.raises(AppError):
        parse_cursor("[1, 2, 3]")  # >2 elements
    with pytest.raises(AppError):
        parse_cursor("['abc']")  # not int
    with pytest.raises(AppError):
        parse_cursor("[true]")  # bool is not allowed


def test_build_project_search_empty():
    body = build_project_search()
    assert body["size"] == 20
    assert body["from"] == 0
    assert body["_source"] == CORE_FIELDS
    assert body["query"] == {"match_all": {}}
    assert "must" not in body["query"].get("bool", {})
    for dis in DISABLED_OBJECTS:
        assert dis not in body["_source"]


def test_build_project_search_filters_and_relevance():
    body = build_project_search(
        q="residency",
        district="Ahmedabad",
        taluka="Ahmedabad City",
        project_type="Residential/Group Housing",
        project_status="Ongoing",
        price="20.97 Lakh Onwards",
        price_prefix="20.9",
        start_from="2015-01-01",
        start_to="2025-12-31",
        end_from="2018-01-01",
        scrape_complete=True,
        docs_downloaded=False,
    )
    query = body["query"]
    assert "bool" in query
    bool_q = query["bool"]

    # must should contain full text multi_match with boosts
    must = bool_q["must"]
    assert len(must) == 1
    assert must[0]["multi_match"]["query"] == "residency"
    assert "project_name^3" in must[0]["multi_match"]["fields"]
    assert "promoter_name^1" in must[0]["multi_match"]["fields"]

    # filter block checks
    filters = bool_q["filter"]
    assert {"term": {"district": "Ahmedabad"}} in filters
    assert {"term": {"taluka": "Ahmedabad City"}} in filters
    assert {"term": {"project_type": "Residential/Group Housing"}} in filters
    assert {"term": {"project_status": "Ongoing"}} in filters
    assert {"term": {"price": "20.97 Lakh Onwards"}} in filters
    assert {"prefix": {"price": "20.9"}} in filters
    assert {"term": {"scrape_status.complete": True}} in filters
    assert {"term": {"scrape_status.docs_downloaded": False}} in filters

    # date ranges format check
    range_filters = [f["range"] for f in filters if "range" in f]
    start_r = next(r["start_date"] for r in range_filters if "start_date" in r)
    assert start_r["format"] == "dd-MM-yyyy"
    assert start_r["gte"] == "01-01-2015"
    assert start_r["lte"] == "31-12-2025"

    end_r = next(r["end_date"] for r in range_filters if "end_date" in r)
    assert end_r["format"] == "dd-MM-yyyy"
    assert end_r["gte"] == "01-01-2018"

    # highlight tags
    hl = body["highlight"]
    assert hl["pre_tags"] == [HIGHLIGHT_PRE]
    assert hl["post_tags"] == [HIGHLIGHT_POST]


def test_build_suggest():
    body = build_suggest("shiva", size=5)
    assert body["size"] == 5
    assert "match_phrase_prefix" in body["query"]
    assert body["query"]["match_phrase_prefix"]["project_name"]["query"] == "shiva"
    with pytest.raises(AppError):
        build_suggest("s")  # < 2 chars


def test_build_facets():
    body = build_facets()
    assert body["size"] == 0
    assert body["track_total_hits"] is False
    assert "districts" in body["aggs"]
    assert "prices" in body["aggs"]
    assert body["aggs"]["prices"]["terms"]["size"] == 15


def test_extract_sections():
    mock_source = {
        "projectId": 573,
        "project_name": "Test Project",
        "Project Profile": {"Overview": "info", "Certificates": []},
        "Project Summary": {"Details": "summary"},
        "Promoters": [{"Name": "Dev"}],
        "Progress & RERA Actions": {},
        "More Projects by The Same Developer": [],
    }
    sections = extract_sections(mock_source)
    assert len(sections) == 5
    for name in DISABLED_OBJECTS:
        assert name in sections
        assert sections[name]["indexed"] is False
    assert sections["Project Profile"]["subsections"] == ["Overview", "Certificates"]
    assert sections["Promoters"]["type"] == "array"


def test_compute_casing_collisions():
    districts = [
        {"key": "Ahmedabad", "doc_count": 5000},
        {"key": "AHmedabad", "doc_count": 1},
        {"key": "Rajkot", "doc_count": 1800},
        {"key": "RAJKOT", "doc_count": 29},
        {"key": "Surat", "doc_count": 2500},
    ]
    res = compute_casing_collisions(districts, [])
    coll = res["districts"]
    assert len(coll) == 2
    norms = {c["normalized"] for c in coll}
    assert "ahmedabad" in norms
    assert "rajkot" in norms

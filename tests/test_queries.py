import pytest
from backend.queries import (
    address_match_score,
    build_project_search,
    build_suggest,
    build_facets,
    build_page,
    build_search_after,
    extract_project_address,
    parse_search_sort,
    parse_sort,
    parse_cursor,
    query_tokens,
    suggest_match_label,
    to_indian_date,
    validate_size,
    validate_page,
    extract_sections,
    compute_casing_collisions,
    CORE_FIELDS,
    PAGE_SOURCE,
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


def test_build_project_search_numeric_id_query():
    body = build_project_search(q="573")
    should = body["query"]["bool"]["should"]
    assert {"term": {"projectId": {"value": 573, "boost": 500}}} in should
    assert body["sort"][0] == {"_score": {"order": "desc"}}


def test_parse_search_sort_prefers_relevance_for_queries():
    assert parse_search_sort(None, True) == [
        {"_score": {"order": "desc"}},
        {"projectId": {"order": "asc"}},
    ]
    assert parse_search_sort(None, False) == [{"projectId": "asc"}]
    assert parse_search_sort("projectId:desc", True) == [{"projectId": "desc"}]


def test_address_helpers():
    source = {"Project Profile": {"Project Overview": {"Project Address": "Near Shahibaug, Ahmedabad"}}}
    assert extract_project_address(source) == "Near Shahibaug, Ahmedabad"
    assert query_tokens("Shivalik Ahmedabad Developers") == ["shivalik", "ahmedabad", "developers"]
    assert address_match_score("Near Shahibaug, Ahmedabad", "shahibaug") > 0
    assert address_match_score("", "shahibaug") == 0
    assert suggest_match_label("573", {"projectId": 573}) == "ID"
    assert suggest_match_label("shiva", {"project_name": "Shivalik Residences"}) == "Project"


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

    assert bool_q["minimum_should_match"] == 1
    should = bool_q["should"]
    multi = next(clause["multi_match"] for clause in should if "multi_match" in clause)
    assert multi["query"] == "residency"
    assert "project_name^4" in multi["fields"]
    assert "promoter_name^3" in multi["fields"]
    assert {"term": {"project_name.keyword": {"value": "residency", "boost": 140}}} in should
    assert body["sort"] == [{"_score": {"order": "desc"}}, {"projectId": {"order": "asc"}}]

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
    should = body["query"]["bool"]["should"]
    assert any(clause.get("match_phrase_prefix", {}).get("project_name", {}).get("query") == "shiva" for clause in should)
    assert any("promoter_name" in clause.get("match_phrase_prefix", {}) for clause in should)
    assert any("district" in clause.get("prefix", {}) for clause in should)
    assert body["sort"] == [{"_score": {"order": "desc"}}, {"projectId": {"order": "asc"}}]
    with pytest.raises(AppError):
        build_suggest("s")


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


def test_build_page():
    body = build_page(page=2, size=15)
    assert body["from"] == 15
    assert body["size"] == 15
    assert body["_source"] == PAGE_SOURCE
    assert body["sort"] == [{"projectId": "asc"}]
    assert body["query"] == {"match_all": {}}


def test_build_search_after():
    body = build_search_after(cursor="[573]", size=25)
    assert body["size"] == 25
    assert body["search_after"] == [573]
    assert body["sort"] == [{"projectId": "asc"}]
    assert "pit" not in body

    body_without_cursor = build_search_after(cursor=None, size=10)
    assert "search_after" not in body_without_cursor


def test_build_project_search_promoter_reg_no_and_doc_range():
    body = build_project_search(
        promoter="SHIVALIK DEVELOPERS",
        reg_no="PR/GJ/AHMEDABAD/123",
        min_documents=10,
        max_documents=50,
        start_from="2020-01-01",
        sort="project_name.keyword:asc",
    )
    filters = body["query"]["bool"]["filter"]
    assert {"term": {"promoter_name.keyword": "SHIVALIK DEVELOPERS"}} in filters
    assert {"term": {"reg_no": "PR/GJ/AHMEDABAD/123"}} in filters
    assert {"range": {"scrape_status.documents": {"gte": 10, "lte": 50}}} in filters

    # single-bound start_date range
    start_r = next(f["range"]["start_date"] for f in filters if "range" in f and "start_date" in f["range"])
    assert start_r["gte"] == "01-01-2020"
    assert "lte" not in start_r

    # explicit sort overrides default relevance/projectId sort
    assert body["sort"] == [{"project_name.keyword": "asc"}, {"projectId": "asc"}]

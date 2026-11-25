import pytest
from backend.queries import (
    address_match_score,
    build_boundary_query,
    build_project_search,
    build_suggest,
    build_facets,
    build_page,
    build_search_after,
    extract_project_address,
    normalize_boundary_query,
    derive_phrase_prefix,
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
    TYPO_MAP,
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
    assert body["track_total_hits"] == 10000
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
    assert {
        "term": {
            "project_name.keyword": {
                "value": "residency",
                "boost": 140,
                "case_insensitive": True,
            }
        }
    } in should
    assert {
        "prefix": {"project_type": {"value": "residency", "boost": 20, "case_insensitive": True}}
    } in should
    assert body["sort"] == [{"_score": {"order": "desc"}}, {"projectId": {"order": "asc"}}]

    # filter block checks
    filters = bool_q["filter"]
    filter_clauses = [
        clause
        for wrapper in filters
        for clause in wrapper.get("bool", {}).get("should", [])
    ]

    def has_case_insensitive_clause(kind: str, field: str, value: str) -> bool:
        return any(
            clause.get(kind, {}).get(field, {}).get("value") == value
            and clause.get(kind, {}).get(field, {}).get("case_insensitive") is True
            for clause in filter_clauses
        )

    assert has_case_insensitive_clause("term", "district", "Ahmedabad")
    assert has_case_insensitive_clause("term", "taluka", "Ahmedabad City")
    assert has_case_insensitive_clause("term", "project_type", "Residential/Group Housing")
    assert has_case_insensitive_clause("term", "project_status", "Ongoing")
    assert has_case_insensitive_clause("term", "price", "20.97 Lakh Onwards")
    assert {"prefix": {"price": {"value": "20.9", "case_insensitive": True}}} in filters
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
    assert any(
        clause.get("prefix", {}).get("district", {}).get("case_insensitive") is True
        for clause in should
    )
    assert body["sort"] == [{"_score": {"order": "desc"}}, {"projectId": {"order": "asc"}}]
    with pytest.raises(AppError):
        build_suggest("s")


@pytest.mark.parametrize("value", ["plot", "Plot", "PLOT", "PLot"])
def test_case_insensitive_exact_and_prefix_queries(value):
    body = build_project_search(q=value, project_type=value, price_prefix=value)
    bool_q = body["query"]["bool"]
    should = bool_q["should"]
    filters = bool_q["filter"]
    filter_clauses = [
        clause
        for wrapper in filters
        for clause in wrapper.get("bool", {}).get("should", [])
    ]

    assert {
        "term": {
            "project_type": {"value": value, "boost": 140, "case_insensitive": True}
        }
    } in should
    assert {
        "prefix": {"project_type": {"value": value, "boost": 20, "case_insensitive": True}}
    } in should
    assert {"term": {"project_type": {"value": value, "case_insensitive": True}}} in filter_clauses
    assert {"prefix": {"project_type": {"value": value, "case_insensitive": True}}} in filter_clauses
    assert {"prefix": {"price": {"value": value, "case_insensitive": True}}} in filters

    suggest_body = build_suggest(value)
    suggest_should = suggest_body["query"]["bool"]["should"]
    assert {
        "prefix": {"project_type": {"value": value, "boost": 3, "case_insensitive": True}}
    } in suggest_should


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
    filter_clauses = [
        clause
        for wrapper in filters
        for clause in wrapper.get("bool", {}).get("should", [])
    ]
    assert {
        "term": {
            "promoter_name.keyword": {
                "value": "SHIVALIK DEVELOPERS",
                "case_insensitive": True,
            }
        }
    } in filter_clauses
    assert {
        "prefix": {
            "promoter_name.keyword": {
                "value": "SHIVALIK DEVELOPERS",
                "case_insensitive": True,
            }
        }
    } in filter_clauses
    assert {
        "term": {"reg_no": {"value": "PR/GJ/AHMEDABAD/123", "case_insensitive": True}}
    } in filter_clauses
    assert {"range": {"scrape_status.documents": {"gte": 10, "lte": 50}}} in filters

    # single-bound start_date range
    start_r = next(f["range"]["start_date"] for f in filters if "range" in f and "start_date" in f["range"])
    assert start_r["gte"] == "01-01-2020"
    assert "lte" not in start_r

    # explicit sort overrides default relevance/projectId sort
    assert body["sort"] == [{"project_name.keyword": "asc"}, {"projectId": "asc"}]


def test_build_boundary_query_uses_only_indexed_filters_and_source_path():
    body = build_boundary_query(
        q="plot",
        district="Ahmedabad",
        project_type="Plotted Development",
        size=500,
        after=573,
    )
    assert body["size"] == 500
    assert body["search_after"] == [573]
    # With q: sort is score-first (new feature contract)
    assert body["sort"] == [{"_score": "desc"}, {"projectId": "asc"}]
    assert "Project Profile.Map Location" in body["_source"]
    assert "Project Profile" not in body["query"]
    assert "geo_distance" not in str(body)
    assert "runtime_mappings" not in str(body)
    # With q + filters: both filter and should are present
    assert body["query"]["bool"]["filter"]
    assert body["query"]["bool"]["should"]


def test_build_boundary_query_rejects_bad_size_and_after():
    with pytest.raises(AppError):
        build_boundary_query(size=0)
    with pytest.raises(AppError):
        build_boundary_query(size=10001)
    with pytest.raises(AppError):
        build_boundary_query(after=-1)


# ---------------------------------------------------------------------------
# New tests for Map Search-to-Centroid feature contracts
# ---------------------------------------------------------------------------

# --- Contract 1 & 2: Normalization and typo map ----------------------------

class TestNormalizeBoundaryQuery:
    """normalize_boundary_query(q) -> (normalized_q, phrase_prefix)"""

    def test_lowercases_text(self):
        norm, _ = normalize_boundary_query("SHIVALIK Residences")
        assert norm == "shivalik residences"

    def test_strips_punctuation(self):
        norm, _ = normalize_boundary_query("shivalik, residences!")
        assert norm == "shivalik residences"

    def test_collapses_whitespace(self):
        norm, _ = normalize_boundary_query("  shivalik   residences  ")
        assert norm == "shivalik residences"

    def test_typo_recidency_corrected(self):
        norm, _ = normalize_boundary_query("shivalik recidency")
        assert norm == "shivalik residency"

    def test_typo_recidancy_corrected(self):
        norm, _ = normalize_boundary_query("recidancy")
        assert norm == "residency"

    def test_typo_recidence_corrected(self):
        norm, _ = normalize_boundary_query("recidence")
        assert norm == "residency"

    def test_typo_recidance_corrected(self):
        norm, _ = normalize_boundary_query("recidance")
        assert norm == "residency"

    def test_typo_map_has_all_four_variants(self):
        for typo in ("recidency", "recidancy", "recidence", "recidance"):
            assert typo in TYPO_MAP
            assert TYPO_MAP[typo] == "residency"

    def test_original_text_not_modified(self):
        # fuzzy matching uses original q, not normalized — normalize returns both
        norm, _ = normalize_boundary_query("shivalik recidency")
        # normalized changes the typo
        assert "recidency" not in norm
        assert "residency" in norm

    def test_no_typo_passthrough(self):
        norm, _ = normalize_boundary_query("shivalik residency")
        assert norm == "shivalik residency"


# --- Contract 3: Phrase-prefix derivation ----------------------------------

class TestDerivePhrasePrefix:
    """derive_phrase_prefix(normalized_q) -> phrase_prefix_str"""

    def test_single_token_full_word_passthrough(self):
        # Short single token: use as-is
        assert derive_phrase_prefix("shivalik") == "shivalik"

    def test_multi_token_prefix_last_five_chars(self):
        # "shivalik residency" -> "shivalik resid" (first 5 chars of "residency")
        assert derive_phrase_prefix("shivalik residency") == "shivalik resid"

    def test_last_token_short_passthrough(self):
        # Last token <= 5 chars: use full token
        assert derive_phrase_prefix("shivalik home") == "shivalik home"

    def test_three_token_prefix(self):
        # three tokens: prefix last
        assert derive_phrase_prefix("green valley residences") == "green valley resid"

    def test_single_short_token(self):
        assert derive_phrase_prefix("abc") == "abc"

    def test_last_token_exactly_five_chars(self):
        # exactly 5 chars: use full token
        assert derive_phrase_prefix("green tower") == "green tower"


# --- Contract 4: Tiered boundary query DSL with q --------------------------

class TestBuildBoundaryQueryWithQ:
    """build_boundary_query(q=...) must emit two-tier bool.should."""

    def test_no_q_keeps_projectid_sort_and_integer_cursor(self):
        body = build_boundary_query(size=100)
        assert body["sort"] == [{"projectId": "asc"}]
        assert "search_after" not in body

    def test_no_q_with_after_uses_integer_cursor(self):
        body = build_boundary_query(size=100, after=573)
        assert body["search_after"] == [573]

    def test_with_q_uses_score_sort(self):
        body = build_boundary_query(q="shivalik residency", size=100)
        sort = body["sort"]
        assert sort[0] == {"_score": "desc"}
        assert sort[1] == {"projectId": "asc"}

    def test_with_q_top_level_minimum_should_match_1(self):
        body = build_boundary_query(q="shivalik residency", size=100)
        assert body["query"]["bool"]["minimum_should_match"] == 1

    def test_with_q_exact_group_has_boost_10(self):
        body = build_boundary_query(q="shivalik residency", size=100)
        should = body["query"]["bool"]["should"]
        mm = next(c["multi_match"] for c in should if "multi_match" in c)
        assert mm["boost"] == 10
        assert mm["type"] == "cross_fields"
        assert mm["lenient"] is True
        assert mm["query"] == "shivalik residency"

    def test_with_q_exact_group_has_project_name_field(self):
        body = build_boundary_query(q="residency", size=100)
        should = body["query"]["bool"]["should"]
        mm = next(c["multi_match"] for c in should if "multi_match" in c)
        assert "project_name^4" in mm["fields"]
        assert "promoter_name^3" in mm["fields"]
        assert "district^3" in mm["fields"]

    def test_with_q_fallback_group_has_boost_1(self):
        body = build_boundary_query(q="shivalik recidency", size=100)
        should = body["query"]["bool"]["should"]
        fallback = next(c["bool"] for c in should if "bool" in c)
        assert fallback["boost"] == 1
        assert fallback["minimum_should_match"] == 1

    def test_with_q_fallback_contains_normalized_exact_match(self):
        body = build_boundary_query(q="shivalik recidency", size=100)
        should = body["query"]["bool"]["should"]
        fallback = next(c["bool"] for c in should if "bool" in c)
        fallback_should = fallback["should"]
        # Normalized: "shivalik residency"
        exact = next(
            c["match"]["project_name"]
            for c in fallback_should
            if "match" in c and "fuzziness" not in c.get("match", {}).get("project_name", {})
        )
        assert exact["query"] == "shivalik residency"
        assert exact["operator"] == "and"
        assert exact["boost"] == 4

    def test_with_q_fallback_contains_phrase_prefix(self):
        body = build_boundary_query(q="shivalik recidency", size=100)
        should = body["query"]["bool"]["should"]
        fallback = next(c["bool"] for c in should if "bool" in c)
        fallback_should = fallback["should"]
        prefix = next(
            c["match_phrase_prefix"]["project_name"]
            for c in fallback_should
            if "match_phrase_prefix" in c
        )
        # phrase prefix of "shivalik residency" -> "shivalik resid"
        assert prefix["query"] == "shivalik resid"
        assert prefix["boost"] == 3

    def test_with_q_fallback_contains_fuzzy_on_original(self):
        body = build_boundary_query(q="shivalik recidency", size=100)
        should = body["query"]["bool"]["should"]
        fallback = next(c["bool"] for c in should if "bool" in c)
        fallback_should = fallback["should"]
        fuzzy = next(
            c["match"]["project_name"]
            for c in fallback_should
            if "match" in c and "fuzziness" in c.get("match", {}).get("project_name", {})
        )
        # fuzzy uses original typo text
        assert fuzzy["query"] == "shivalik recidency"
        assert fuzzy["fuzziness"] == "AUTO"
        assert fuzzy["prefix_length"] == 1
        assert fuzzy["max_expansions"] == 25
        assert fuzzy["operator"] == "and"
        assert fuzzy["boost"] == 1

    def test_with_q_no_scripts_regexp_runtime_mappings(self):
        body = build_boundary_query(q="shivalik recidency", size=100)
        body_str = str(body)
        assert "script" not in body_str
        assert "regexp" not in body_str
        assert "runtime_mappings" not in body_str

    def test_with_q_score_cursor_is_list_of_two(self):
        # after cursor with q should accept [score, projectId] format encoded as JSON
        body = build_boundary_query(q="shivalik residency", size=100, after_cursor="[333, 573]")
        assert body["search_after"] == [333, 573]

    def test_without_q_integer_after_still_works(self):
        body = build_boundary_query(size=100, after=573)
        assert body["search_after"] == [573]

    def test_with_q_filters_coexist(self):
        body = build_boundary_query(q="residency", district="Ahmedabad", size=100)
        # filters AND should both present
        assert body["query"]["bool"]["filter"]
        assert body["query"]["bool"]["should"]

    def test_existing_boundary_source_path_preserved(self):
        body = build_boundary_query(q="residency", size=100)
        assert "Project Profile.Map Location" in body["_source"]


# --- Contract 5: Pinned-row count / route metadata -------------------------

class TestBoundaryQueryScoreExposure:
    """score field in build_boundary_query metadata when q is present."""

    def test_query_has_track_total_hits(self):
        body = build_boundary_query(q="residency", size=100)
        assert body.get("track_total_hits") == 10000

    def test_no_q_still_has_track_total_hits(self):
        body = build_boundary_query(size=100)
        assert body.get("track_total_hits") == 10000


# --- Existing boundary test updated for new after_cursor param -------------

def test_build_boundary_query_rejects_bad_after_cursor():
    # integer after still raises on negative
    with pytest.raises(AppError):
        build_boundary_query(after=-1)
    # score cursor: invalid JSON
    with pytest.raises(AppError):
        build_boundary_query(q="test", after_cursor="notjson")
    # score cursor: not a list
    with pytest.raises(AppError):
        build_boundary_query(q="test", after_cursor="573")
    # score cursor: too many elements
    with pytest.raises(AppError):
        build_boundary_query(q="test", after_cursor="[1, 2, 3]")

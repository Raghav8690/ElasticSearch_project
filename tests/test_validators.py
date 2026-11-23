import pytest
from backend.routes import _validate_console_body, require_index
from backend.schemas import AppError


def test_require_index():
    # Valid index does not raise
    require_index("gujrat_rera_data")

    # Invalid index raises forbidden
    with pytest.raises(AppError) as exc:
        require_index("other_index")
    assert exc.value.code == "forbidden"
    assert exc.value.status_code == 403


def test_validate_console_body_valid():
    body = {
        "query": {"match_all": {}},
        "size": 20,
        "from": 10,
        "sort": [{"projectId": "asc"}],
        "_source": ["projectId", "project_name"],
    }
    # Valid body does not raise
    _validate_console_body(body)


def test_validate_console_body_forbidden_keys():
    # Top-level disallowed key
    with pytest.raises(AppError) as exc:
        _validate_console_body({"query": {}, "script_fields": {}})
    assert exc.value.code == "invalid_request"
    assert "not allowed in console queries" in exc.value.message


def test_validate_console_body_nested_script():
    # Nested script clause
    body = {
        "query": {
            "bool": {
                "filter": [
                    {"script": {"script": {"source": "doc['price'].value"}}}
                ]
            }
        }
    }
    with pytest.raises(AppError) as exc:
        _validate_console_body(body)
    assert exc.value.code == "invalid_request"
    assert "script" in exc.value.message


def test_validate_console_body_nested_regexp():
    body = {
        "query": {
            "regexp": {"project_name": "res.*"}
        }
    }
    with pytest.raises(AppError) as exc:
        _validate_console_body(body)
    assert "regexp" in exc.value.message


def test_validate_console_body_leading_wildcard():
    body = {
        "query": {
            "wildcard": {"project_name": "*residency"}
        }
    }
    with pytest.raises(AppError) as exc:
        _validate_console_body(body)
    assert "wildcard" in exc.value.message.lower()


def test_validate_console_body_size_caps():
    with pytest.raises(AppError) as exc:
        _validate_console_body({"size": 101})
    assert "size must be <= 100" in exc.value.message

    with pytest.raises(AppError) as exc:
        _validate_console_body({"size": 50, "from": 9980})
    assert "10000" in exc.value.message


def test_validate_console_body_disabled_object_source():
    # Attempting to fetch disabled object Project Profile in console
    with pytest.raises(AppError) as exc:
        _validate_console_body({"_source": ["projectId", "Project Profile"]})
    assert "disabled object" in exc.value.message.lower()

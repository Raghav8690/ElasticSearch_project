from backend.slowlog import SlowQueryLog


def test_slow_query_log_records_newest_first_and_marks_slow():
    log = SlowQueryLog(capacity=5, threshold_ms=100)
    log.record(route="/api/projects/search", wall_ms=50)
    log.record(route="/api/query/gujrat_rera_data", wall_ms=150, q="hello")

    snapshot = log.snapshot()

    assert snapshot["count"] == 2
    assert snapshot["slow_count"] == 1
    assert snapshot["threshold_ms"] == 100
    assert snapshot["entries"][0]["route"] == "/api/query/gujrat_rera_data"
    assert snapshot["entries"][0]["q"] == "hello"
    assert snapshot["entries"][0]["slow"] is True
    assert snapshot["entries"][1]["slow"] is False


def test_slow_query_log_is_bounded():
    log = SlowQueryLog(capacity=2, threshold_ms=100)
    for index in range(5):
        log.record(route=f"/route-{index}", wall_ms=10)

    snapshot = log.snapshot()

    assert snapshot["capacity"] == 2
    assert snapshot["count"] == 2
    assert [entry["route"] for entry in snapshot["entries"]] == ["/route-4", "/route-3"]

import pytest

from backend.geometry import (
    bbox_overlap,
    boundary_item,
    close_ring,
    haversine_km,
    matches_geometry,
    normalize_ring,
    parse_bbox,
    parse_polygon,
    parse_radius,
    point_in_polygon,
    ring_bounds,
    ring_center,
    unique_points,
)
from backend.schemas import AppError


def test_normalize_ring_dedupes_and_closes():
    raw = [
        {"lat": "22.0", "lng": "72.0"},
        {"lat": "22.0", "lng": "72.1"},
        {"lat": "22.1", "lng": "72.1"},
        {"lat": "22.1", "lng": "72.0"},
        {"lat": "22.0", "lng": "72.0"},
    ]
    ring, reason = normalize_ring(raw)
    assert reason is None
    assert ring == [(22.0, 72.0), (22.0, 72.1), (22.1, 72.1), (22.1, 72.0), (22.0, 72.0)]
    assert len(unique_points(ring)) == 4
    assert close_ring([(0.0, 0.0), (0.0, 1.0), (1.0, 1.0)])[-1] == (0.0, 0.0)


def test_normalize_ring_rejects_degenerate_and_unparseable():
    assert normalize_ring([{"lat": "22", "lng": "72"}] * 3) == (None, "degenerate")
    assert normalize_ring([{"lat": "bad", "lng": "72"}]) == (None, "unparseable")


def test_bounds_center_and_containment():
    ring = [(22.0, 72.0), (22.0, 72.2), (22.2, 72.2), (22.2, 72.0), (22.0, 72.0)]
    assert ring_bounds(ring) == (72.0, 22.0, 72.2, 22.2)
    assert ring_center(ring) == pytest.approx((22.1, 72.1))
    assert point_in_polygon((22.1, 72.1), ring) is True
    assert point_in_polygon((23.0, 73.0), ring) is False
    assert bbox_overlap((72.0, 22.0, 72.2, 22.2), (72.1, 22.1, 72.3, 22.3)) is True
    assert bbox_overlap((72.0, 22.0, 72.2, 22.2), (73.0, 23.0, 73.2, 23.2)) is False


def test_haversine_and_geometry_filters():
    assert haversine_km((22.0, 72.0), (22.0, 72.0)) == pytest.approx(0.0)
    assert haversine_km((22.0, 72.0), (23.0, 72.0)) == pytest.approx(111.2, abs=0.5)
    ring = [(22.0, 72.0), (22.0, 72.2), (22.2, 72.2), (22.2, 72.0), (22.0, 72.0)]
    assert matches_geometry(
        (22.1, 72.1),
        ring_bounds(ring),
        bbox=(72.0, 22.0, 72.2, 22.2),
        radius=((22.1, 72.1), 5.0),
        polygon=ring,
    )
    assert not matches_geometry(
        (22.1, 72.1),
        ring_bounds(ring),
        bbox=None,
        radius=((23.0, 72.0), 5.0),
        polygon=None,
    )
    assert not matches_geometry(
        (22.1, 72.1),
        ring_bounds(ring),
        bbox=None,
        radius=None,
        polygon=[(23.0, 73.0), (23.0, 73.1), (23.1, 73.1)],
    )


def test_geometry_parameter_parsing():
    assert parse_bbox("72.0,22.0,72.2,22.2") == (72.0, 22.0, 72.2, 22.2)
    assert parse_radius("22.1", "72.1", "5") == ((22.1, 72.1), 5.0)
    assert parse_polygon("22.0,72.0;22.0,72.2;22.2,72.2") == [
        (22.0, 72.0),
        (22.0, 72.2),
        (22.2, 72.2),
        (22.0, 72.0),
    ]
    with pytest.raises(AppError):
        parse_bbox("72.2,22.2,72.0,22.0")
    with pytest.raises(AppError):
        parse_radius("22.1", "72.1", None)
    with pytest.raises(AppError):
        parse_polygon("22.0,72.0;22.0,72.1")


def test_boundary_item_feature_and_marker():
    source = {
        "projectId": 573,
        "project_name": "Shivalik Residences",
        "district": "Ahmedabad",
        "Project Profile": {
            "Map Location": [
                {"lat": "22.0", "lng": "72.0"},
                {"lat": "22.0", "lng": "72.1"},
                {"lat": "22.1", "lng": "72.1"},
            ]
        },
    }
    feature, marker, reason = boundary_item(source)
    assert reason is None
    assert marker is None
    assert feature["id"] == 573
    assert len(feature["ring"]) == 4

    source["Project Profile"]["Map Location"] = [{"lat": "22.0", "lng": "72.0"}]
    feature, marker, reason = boundary_item(source)
    assert feature is None
    assert marker["center"] == [22.0, 72.0]
    assert reason == "degenerate"

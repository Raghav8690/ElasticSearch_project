from __future__ import annotations

import math
from typing import Any

from .schemas import AppError

Point = tuple[float, float]
BBox = tuple[float, float, float, float]


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _same_point(a: Point, b: Point) -> bool:
    return abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9


def parse_ring(raw: Any) -> list[Point]:
    if not isinstance(raw, list):
        return []
    points: list[Point] = []
    for item in raw:
        if not isinstance(item, dict):
            return []
        lat = _finite(item.get("lat"))
        lng = _finite(item.get("lng"))
        if lat is None or lng is None or abs(lat) > 90 or abs(lng) > 180:
            return []
        points.append((lat, lng))
    return points


def unique_points(points: list[Point]) -> list[Point]:
    seen: set[tuple[float, float]] = set()
    unique: list[Point] = []
    for point in points:
        key = (round(point[0], 7), round(point[1], 7))
        if key in seen:
            continue
        seen.add(key)
        unique.append(point)
    return unique


def close_ring(points: list[Point]) -> list[Point]:
    if len(points) >= 2 and not _same_point(points[0], points[-1]):
        return points + [points[0]]
    return points


def normalize_ring(raw: Any) -> tuple[list[Point] | None, str | None]:
    points = parse_ring(raw)
    if not points:
        return None, "unparseable"
    unique = unique_points(points)
    if len(unique) < 3:
        return None, "degenerate"
    return close_ring(unique), None


def ring_bounds(points: list[Point]) -> BBox:
    lats = [point[0] for point in points]
    lngs = [point[1] for point in points]
    return min(lngs), min(lats), max(lngs), max(lats)


def ring_center(points: list[Point]) -> Point:
    unique = unique_points(points)
    lats = [point[0] for point in unique]
    lngs = [point[1] for point in unique]
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


def bbox_overlap(a: BBox, b: BBox) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def haversine_km(a: Point, b: Point) -> float:
    radius = 6371.0088
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(h)))


def point_in_polygon(point: Point, ring: list[Point]) -> bool:
    lat, lng = point
    inside = False
    previous = len(ring) - 1
    for current in range(len(ring)):
        y1, x1 = ring[current]
        y2, x2 = ring[previous]
        if (y1 > lat) != (y2 > lat):
            crossing = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lng < crossing:
                inside = not inside
        previous = current
    return inside


def parse_bbox(value: str | None) -> BBox | None:
    if not value:
        return None
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise AppError("invalid_request", "bbox must be minLng,minLat,maxLng,maxLat.")
    numbers = [_finite(part) for part in parts]
    if any(number is None for number in numbers):
        raise AppError("invalid_request", "bbox values must be numeric.")
    min_lng, min_lat, max_lng, max_lat = (number for number in numbers if number is not None)
    if not (-180 <= min_lng <= 180 and -180 <= max_lng <= 180 and -90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise AppError("invalid_request", "bbox coordinates are outside valid lat/lng ranges.")
    if min_lng >= max_lng or min_lat >= max_lat:
        raise AppError("invalid_request", "bbox minimums must be smaller than maximums.")
    return min_lng, min_lat, max_lng, max_lat


def parse_radius(lat: str | None, lon: str | None, distance_km: str | None) -> tuple[Point, float] | None:
    values = (lat, lon, distance_km)
    if not any(values):
        return None
    if not all(values):
        raise AppError("invalid_request", "radius filtering requires lat, lon, and distance_km.")
    lat_value = _finite(lat)
    lng_value = _finite(lon)
    distance_value = _finite(distance_km)
    if lat_value is None or lng_value is None or distance_value is None:
        raise AppError("invalid_request", "radius values must be numeric.")
    if abs(lat_value) > 90 or abs(lng_value) > 180:
        raise AppError("invalid_request", "radius coordinates are outside valid lat/lng ranges.")
    if distance_value <= 0 or distance_value > 200:
        raise AppError("invalid_request", "distance_km must be between 0 and 200.")
    return (lat_value, lng_value), distance_value


def parse_polygon(value: str | None) -> list[Point] | None:
    if not value:
        return None
    points: list[Point] = []
    for part in value.split(";"):
        pair = [item.strip() for item in part.split(",")]
        if len(pair) != 2:
            raise AppError("invalid_request", "polygon must use lat,lng;lat,lng;... format.")
        lat = _finite(pair[0])
        lng = _finite(pair[1])
        if lat is None or lng is None or abs(lat) > 90 or abs(lng) > 180:
            raise AppError("invalid_request", "polygon coordinates are outside valid lat/lng ranges.")
        points.append((lat, lng))
    if len(unique_points(points)) < 3:
        raise AppError("invalid_request", "polygon requires at least three distinct points.")
    return close_ring(points)


def matches_geometry(
    center: Point,
    bounds: BBox,
    *,
    bbox: BBox | None,
    radius: tuple[Point, float] | None,
    polygon: list[Point] | None,
) -> bool:
    if bbox is not None and not bbox_overlap(bounds, bbox):
        return False
    if radius is not None:
        origin, distance_km = radius
        if haversine_km(origin, center) > distance_km:
            return False
    if polygon is not None and not point_in_polygon(center, polygon):
        return False
    return True


def boundary_item(source: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    profile = source.get("Project Profile") or {}
    raw = profile.get("Map Location") if isinstance(profile, dict) else None
    ring, reason = normalize_ring(raw)
    points = ring if ring is not None else parse_ring(raw)
    if not points:
        return None, None, reason or "unparseable"
    center = ring_center(points)
    bounds = ring_bounds(points)
    base = {
        "id": source.get("projectId"),
        "name": source.get("project_name"),
        "district": source.get("district"),
        "taluka": source.get("taluka"),
        "project_type": source.get("project_type"),
        "project_status": source.get("project_status"),
        "reg_no": source.get("reg_no"),
        "center": [round(center[0], 6), round(center[1], 6)],
        "bbox": [round(value, 6) for value in bounds],
    }
    if ring is None:
        return None, base, reason
    base["ring"] = [[round(lat, 6), round(lng, 6)] for lat, lng in ring]
    return base, None, None

"""좌표 계산 유틸리티 (컴포넌트가 아닌 공용 함수)."""
from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이 거리(m)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def round_coord(value: float) -> float:
    """방문지 중심 좌표는 소수점 4자리(약 10m)까지만 보관 (DR-02, DR-08)."""
    return round(value, 4)

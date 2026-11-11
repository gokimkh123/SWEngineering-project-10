"""CP-09 Visit Clusterer (Analysis 계층, 순수 로직).

책임: DBSCAN으로 사진을 방문지로 묶고 중심 좌표·시각·순서·대표 사진을 계산, 날짜별로 나눈다 (FR-02).
위치 있는 사진이 하나도 없으면 촬영 시각만으로 나눈다 (UC-01 5b).
의존: 없음 (scikit-learn 라이브러리만 사용) → 단위 테스트 대상.

임계값(거리 200m, 시간 60분)은 요구사항분석서 2.5에 따라 스프린트 1 PoC 후 확정한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
from sklearn.cluster import DBSCAN

from app.geo import haversine_m, round_coord

DIST_EPS_M = 200.0
TIME_EPS_MIN = 60.0
TIME_ONLY_GAP_MIN = 60.0


@dataclass(frozen=True)
class PhotoPoint:
    photo_id: str
    taken_at: datetime | None
    lat: float | None
    lng: float | None

    @property
    def has_gps(self) -> bool:
        return self.lat is not None and self.lng is not None


@dataclass
class VisitCluster:
    order: int
    day: int
    date: date
    photo_ids: list[str]
    start_at: datetime
    end_at: datetime
    center_lat: float | None
    center_lng: float | None
    rep_photo_id: str

    @property
    def photo_count(self) -> int:
        return len(self.photo_ids)


@dataclass
class ClusterResult:
    visits: list[VisitCluster]
    untagged_ids: list[str] = field(default_factory=list)  # 시각은 있지만 위치 없는 사진 → CP-12
    no_info_ids: list[str] = field(default_factory=list)  # 시각·위치 모두 없음 → 사용자 확인
    time_only: bool = False  # 위치 있는 사진이 하나도 없어 시각으로만 묶음


def _distance_matrix(points: list[PhotoPoint]) -> np.ndarray:
    """두 사진 사이 거리 = max(거리/200m, 시간차/60분). 1 이하이면 같은 방문지 후보."""
    n = len(points)
    m = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            a, b = points[i], points[j]
            d = haversine_m(a.lat, a.lng, b.lat, b.lng) / DIST_EPS_M
            t = abs((a.taken_at - b.taken_at).total_seconds()) / 60.0 / TIME_EPS_MIN
            m[i, j] = m[j, i] = max(d, t)
    return m


def _make_visit(points: list[PhotoPoint]) -> dict:
    points = sorted(points, key=lambda p: p.taken_at)
    gps = [p for p in points if p.has_gps]
    if gps:
        clat = sum(p.lat for p in gps) / len(gps)
        clng = sum(p.lng for p in gps) / len(gps)
        # 대표 사진: 중심에 가장 가까운 사진 (같으면 앞선 사진)
        rep = min(gps, key=lambda p: haversine_m(p.lat, p.lng, clat, clng))
        clat, clng = round_coord(clat), round_coord(clng)
    else:
        clat = clng = None
        rep = points[len(points) // 2]
    return {
        "photo_ids": [p.photo_id for p in points],
        "start_at": points[0].taken_at,
        "end_at": points[-1].taken_at,
        "center_lat": clat,
        "center_lng": clng,
        "rep_photo_id": rep.photo_id,
    }


def _cluster_gps_points(points: list[PhotoPoint]) -> list[list[PhotoPoint]]:
    if len(points) == 1:
        return [points]
    labels = DBSCAN(eps=1.0, min_samples=1, metric="precomputed").fit_predict(_distance_matrix(points))
    groups: dict[int, list[PhotoPoint]] = {}
    for label, p in zip(labels, points):
        groups.setdefault(int(label), []).append(p)
    return list(groups.values())


def _split_by_time_gap(points: list[PhotoPoint]) -> list[list[PhotoPoint]]:
    points = sorted(points, key=lambda p: p.taken_at)
    groups: list[list[PhotoPoint]] = []
    for p in points:
        if groups and (p.taken_at - groups[-1][-1].taken_at) <= timedelta(minutes=TIME_ONLY_GAP_MIN):
            groups[-1].append(p)
        else:
            groups.append([p])
    return groups


def cluster_photos(photos: list[PhotoPoint]) -> ClusterResult:
    """사진 목록을 방문지로 묶는다."""
    timed = [p for p in photos if p.taken_at is not None]
    no_info = [p.photo_id for p in photos if p.taken_at is None and not p.has_gps]
    # 촬영 시각 없이 위치만 있는 사진은 날짜를 정할 수 없어 첫 사진 시각으로 보정하지 않고 제외 후보로 둔다
    no_info += [p.photo_id for p in photos if p.taken_at is None and p.has_gps]

    gps_points = [p for p in timed if p.has_gps]
    raw_groups: list[list[PhotoPoint]] = []
    untagged: list[str] = []
    time_only = False

    if gps_points:
        by_date: dict[date, list[PhotoPoint]] = {}
        for p in gps_points:
            by_date.setdefault(p.taken_at.date(), []).append(p)
        for d in sorted(by_date):
            raw_groups.extend(_cluster_gps_points(by_date[d]))
        untagged = [p.photo_id for p in timed if not p.has_gps]
    elif timed:
        time_only = True
        by_date = {}
        for p in timed:
            by_date.setdefault(p.taken_at.date(), []).append(p)
        for d in sorted(by_date):
            raw_groups.extend(_split_by_time_gap(by_date[d]))

    built = sorted((_make_visit(g) for g in raw_groups), key=lambda v: v["start_at"])
    dates = sorted({v["start_at"].date() for v in built})
    day_index = {d: i + 1 for i, d in enumerate(dates)}
    visits = [
        VisitCluster(order=i + 1, day=day_index[v["start_at"].date()], date=v["start_at"].date(), **v)
        for i, v in enumerate(built)
    ]
    return ClusterResult(visits=visits, untagged_ids=untagged, no_info_ids=no_info, time_only=time_only)

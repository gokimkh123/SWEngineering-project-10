"""CP-12 Untagged Photo Resolver (Analysis 계층).

책임: 위치 없는 사진의 방문지 추천 — 촬영 시각 보간, 애매하면 VLM 비교 (FR-06, UC-03).
최종 배정은 사용자가 확인한다 (B3 화면).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.adapters.cp19_ai_gateway import AIError, AIGateway

WITHIN_MARGIN = timedelta(minutes=20)  # 방문 시간대 앞뒤 20분 안이면 그 방문지
AMBIGUOUS_RATIO = 1.5  # 앞뒤 방문지까지 시간 차가 1.5배 안쪽이면 애매하다고 본다


@dataclass
class VisitSpan:
    visit_id: str
    name: str
    start_at: datetime
    end_at: datetime


@dataclass
class Suggestion:
    visit_id: str | None
    reason: str
    method: str  # time | vlm | none
    neighbors: list[str] | None = None  # VLM 비교 대상 (애매한 경우)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def suggest_by_time(taken_at: datetime | None, spans: list[VisitSpan]) -> Suggestion:
    """촬영 시각만으로 추천한다. 애매하면 method='vlm'과 비교 대상 두 방문지를 돌려준다 (순수 함수)."""
    if taken_at is None or not spans:
        return Suggestion(None, "촬영 시각 정보가 없어 직접 골라 주세요", "none")
    same_day = [s for s in spans if s.start_at.date() == taken_at.date()] or spans
    for s in same_day:
        if s.start_at - WITHIN_MARGIN <= taken_at <= s.end_at + WITHIN_MARGIN:
            return Suggestion(s.visit_id, f"{_fmt(taken_at)} 촬영 — {s.name} 방문 시간({_fmt(s.start_at)}~{_fmt(s.end_at)})과 겹쳐요", "time")
    before = [s for s in same_day if s.end_at <= taken_at]
    after = [s for s in same_day if s.start_at >= taken_at]
    prev = max(before, key=lambda s: s.end_at) if before else None
    nxt = min(after, key=lambda s: s.start_at) if after else None
    if prev and not nxt:
        return Suggestion(prev.visit_id, f"{_fmt(taken_at)} 촬영 — 마지막 방문지 {prev.name} 이후에 찍었어요", "time")
    if nxt and not prev:
        return Suggestion(nxt.visit_id, f"{_fmt(taken_at)} 촬영 — 첫 방문지 {nxt.name} 직전에 찍었어요", "time")
    gap_prev = (taken_at - prev.end_at).total_seconds()
    gap_next = (nxt.start_at - taken_at).total_seconds()
    near, far, g_near, g_far = (prev, nxt, gap_prev, gap_next) if gap_prev <= gap_next else (nxt, prev, gap_next, gap_prev)
    if g_far >= g_near * AMBIGUOUS_RATIO:
        return Suggestion(near.visit_id,
                          f"{_fmt(taken_at)} 촬영 — {prev.name}({_fmt(prev.end_at)})와 {nxt.name}({_fmt(nxt.start_at)}) 사이로, {near.name}에 더 가까운 시각이에요",
                          "time")
    return Suggestion(None, f"{_fmt(taken_at)} 촬영 — {prev.name}와 {nxt.name} 사이 중간 시각이라 사진을 비교해요", "vlm",
                      neighbors=[prev.visit_id, nxt.visit_id])


class UntaggedPhotoResolver:
    def __init__(self, gateway: AIGateway) -> None:
        self.gateway = gateway

    def resolve(self, taken_at: datetime | None, spans: list[VisitSpan], image: bytes | None,
                neighbor_images: dict[str, bytes]) -> Suggestion:
        s = suggest_by_time(taken_at, spans)
        if s.method != "vlm":
            return s
        names = {sp.visit_id: sp.name for sp in spans}
        neighbors = [(vid, names[vid], neighbor_images[vid]) for vid in s.neighbors or [] if vid in neighbor_images]
        if image is None or len(neighbors) < 2:
            # 비교할 사진이 없으면 시간상 앞 방문지를 추천하고 사용자가 확인
            return Suggestion(s.neighbors[0], s.reason + " (사진 비교 불가, 앞 방문지 추천)", "time")
        try:
            data = json.loads(self.gateway.vlm_compare(image, neighbors))
            vid = data.get("visit_id")
            if vid not in names:
                raise ValueError("방문지 목록 밖 응답")
            return Suggestion(vid, f"{s.reason} → AI 비교: {data.get('reason', '')}", "vlm")
        except (AIError, ValueError, TypeError):
            return Suggestion(s.neighbors[0], s.reason + " (AI 비교 실패, 앞 방문지 추천)", "time")

"""CP-11 Place Matcher (Analysis 계층).

책임: VLM 판별 요청, 후보 안 답인지 검증·1회 재요청, 확신도 라우팅, 매칭 로그 기록
(FR-04, AIR-02, AIR-03, QA-02, DR-09). VLM이 후보 밖 장소를 답하면 코드가 거부한다 (closed-set).

확신도 임계값(0.8 / 0.5)은 요구사항분석서 FR-04 기준이며 PoC 후 조정할 수 있게 환경변수로 뺐다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from app.adapters.cp19_ai_gateway import VLM_MATCH_PROMPT, AIError, AIGateway
from app.models import MatchLog, Visit, VisitStatus

AUTO_THRESHOLD = float(os.environ.get("MATCH_AUTO_THRESHOLD", "0.8"))
CHECK_THRESHOLD = float(os.environ.get("MATCH_CHECK_THRESHOLD", "0.5"))
NONE_ID = "none"


@dataclass
class VlmAnswer:
    place_id: str | None  # None = "없음"
    confidence: float
    reason: str


class InvalidVlmResponse(ValueError):
    pass


def parse_vlm_response(raw: str, candidate_ids: set[str]) -> VlmAnswer:
    """응답 형식과 closed-set을 검사한다 (AIR-02). 틀리면 InvalidVlmResponse."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as e:
        raise InvalidVlmResponse("JSON 형식이 아니에요") from e
    if not isinstance(data, dict) or set(data) - {"place_id", "confidence", "reason"} or "place_id" not in data:
        raise InvalidVlmResponse("정해진 필드가 아니에요")
    pid = data.get("place_id")
    conf = data.get("confidence")
    reason = data.get("reason") or ""
    if not isinstance(pid, str) or not isinstance(conf, (int, float)) or isinstance(conf, bool) or not isinstance(reason, str):
        raise InvalidVlmResponse("필드 타입이 맞지 않아요")
    if not 0.0 <= float(conf) <= 1.0:
        raise InvalidVlmResponse("확신도가 0~1 범위를 벗어났어요")
    if pid == NONE_ID:
        return VlmAnswer(None, float(conf), reason)
    if pid not in candidate_ids:
        raise InvalidVlmResponse(f"후보 목록에 없는 장소예요 ({pid})")
    return VlmAnswer(pid, float(conf), reason)


def route(answer: VlmAnswer | None) -> VisitStatus:
    """확신도 라우팅 (FR-04): 0.8 이상 자동확정, 0.5 이상 확인필요, 그 밖은 선택필요."""
    if answer is None or answer.place_id is None:
        return VisitStatus.NEEDS_SELECTION
    if answer.confidence >= AUTO_THRESHOLD:
        return VisitStatus.AUTO_CONFIRMED
    if answer.confidence >= CHECK_THRESHOLD:
        return VisitStatus.NEEDS_CHECK
    return VisitStatus.NEEDS_SELECTION


class PlaceMatcher:
    def __init__(self, gateway: AIGateway) -> None:
        self.gateway = gateway

    def ask(self, image: bytes, candidates: list[dict]) -> tuple[VlmAnswer | None, str | None]:
        """VLM에 묻고 검증한다. 형식·후보 오류는 1회 재요청, 다시 실패하면 (None, 사유) (AIR-03)."""
        ids = {c["place_id"] for c in candidates}
        last_error = None
        for _ in range(2):
            try:
                raw = self.gateway.vlm_match(image, candidates)
                return parse_vlm_response(raw, ids), None
            except InvalidVlmResponse as e:
                last_error = f"AI 응답 오류: {e}"
            except AIError as e:
                last_error = str(e)
        return None, last_error

    def apply(self, visit: Visit, answer: VlmAnswer | None, error: str | None) -> list[MatchLog]:
        """방문지 상태를 정하고 매칭 로그를 남긴다. 로그에는 사진·좌표를 넣지 않는다 (DR-09)."""
        status = route(answer)
        visit.status = status.value
        visit.ai_place_id = answer.place_id if answer else None
        visit.confidence = answer.confidence if answer else None
        visit.ai_reason = answer.reason if answer else None
        visit.place_id = answer.place_id if status == VisitStatus.AUTO_CONFIRMED else None
        if error:
            visit.note = error
        elif answer and answer.place_id is None:
            visit.note = "AI가 맞는 후보가 없다고 답했어요"
        return [MatchLog(visit_id=visit.id, event="ai", ai_place_id=visit.ai_place_id,
                         confidence=visit.confidence, prompt_version=VLM_MATCH_PROMPT)]

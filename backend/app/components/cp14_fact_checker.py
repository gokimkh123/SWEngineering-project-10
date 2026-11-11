"""CP-14 Fact Checker (Domain 공용 모듈, 순수 로직).

책임: 여행기 문장의 장소 ID·필드 값을 공식 데이터와 대조한다 (FR-09, FR-10, AIR-06, UC-09).
- 생성 문장: 근거 장소가 확정 방문지인지, 사실 문장에 근거 필드가 있는지, 문장 속 숫자·시간이 근거 값에 있는지
- 편집 문장: 장소명과 시간·요금·거리 같은 수치 표현만 대조
AI를 쓰지 않고 코드로만 처리한다. 의존: 없음 → 단위 테스트 대상.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_TIME_RE = re.compile(r"(\d{1,2})\s*:\s*(\d{2})")
_KOR_TIME_RE = re.compile(r"(오전|오후|밤|저녁|아침|새벽)?\s*(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?(?!간|대|즈음)")
_MONEY_RE = re.compile(r"(\d[\d,]*)\s*원")
_DIST_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(km|㎞|m|미터|킬로미터)(?![a-zA-Z])")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


@dataclass
class Warning:
    code: str
    message: str

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


@dataclass
class CheckResult:
    warnings: list[Warning] = field(default_factory=list)
    is_fact: bool = False

    @property
    def ok(self) -> bool:
        return not self.warnings


def _norm_time(h: int, m: int) -> str:
    return f"{h % 24:02d}:{m:02d}"


def time_tokens(text: str) -> set[str]:
    out = {_norm_time(int(h), int(m)) for h, m in _TIME_RE.findall(text)}
    for ampm, h, m in _KOR_TIME_RE.findall(text):
        hour = int(h)
        if ampm in ("오후", "밤", "저녁") and hour < 12:
            hour += 12
        out.add(_norm_time(hour, int(m or 0)))
    return out


def money_tokens(text: str) -> set[int]:
    return {int(x.replace(",", "")) for x in _MONEY_RE.findall(text) if x.replace(",", "").isdigit()}


def distance_tokens(text: str) -> set[float]:
    out = set()
    for num, unit in _DIST_RE.findall(text):
        v = float(num)
        out.add(round(v * 1000 if unit in ("km", "㎞", "킬로미터") else v, 1))
    return out


def number_tokens(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUM_RE.findall(text)}


def looks_factual(text: str) -> bool:
    """LLM이 사실 문장 표시를 빼먹어도 숫자·사실 단서가 있으면 사실 문장으로 본다 (AIR-06)."""
    return bool(_NUM_RE.search(text)) or any(h in text for h in ("운영", "요금", "입장료", "개장", "휴무", "주소", "길이"))


def _mentioned_names(text: str, known_names: dict[str, str]) -> set[str]:
    """문장에 나온 알려진 장소 이름 → 장소 ID 집합 (긴 이름 우선)."""
    found: set[str] = set()
    rest = text
    for name in sorted(known_names, key=len, reverse=True):
        if len(name) >= 2 and name in rest:
            found.add(known_names[name])
            rest = rest.replace(name, " ")
    return found


def check_generated_sentence(
    text: str,
    place_ids: list[str],
    fields: list[str],
    declared_fact: bool,
    facts: dict[str, dict[str, str]],
    confirmed_ids: set[str],
    known_names: dict[str, str],
) -> CheckResult:
    """LLM이 만든 문장 하나를 대조한다.

    facts: {장소 ID: {필드: 값}} — LLM에 넣었던 확정 장소의 공식 데이터
    known_names: {장소 이름: 장소 ID} — 확정 장소와 후보로 조회됐던 장소 이름
    """
    result = CheckResult(is_fact=declared_fact or looks_factual(text))

    for pid in place_ids:
        if pid not in confirmed_ids:
            result.warnings.append(Warning("unconfirmed_place", "확정되지 않은 장소를 근거로 들었어요"))

    for pid in _mentioned_names(text, known_names) - confirmed_ids:
        result.warnings.append(Warning("unvisited_place", "이번 여행에서 확정되지 않은 장소가 나와요"))

    if not result.is_fact:
        return result

    cited = [(pid, f) for pid in place_ids for f in fields if pid in facts]
    values = [facts[pid][f] for pid, f in cited if f in facts[pid]]
    if not values:
        result.warnings.append(Warning("no_source", "근거 데이터가 없는 사실 문장이에요"))
        return result

    joined = " ".join(values)
    if not number_tokens(text) <= number_tokens(joined):
        missing = sorted(number_tokens(text) - number_tokens(joined))
        result.warnings.append(Warning("number_mismatch", f"공식 데이터에 없는 수치가 있어요: {', '.join(missing)}"))
    return result


def check_edited_sentence(
    text: str,
    facts: dict[str, dict[str, str]],
    confirmed_ids: set[str],
    known_names: dict[str, str],
    context_place_ids: list[str] | None = None,
) -> CheckResult:
    """사용자가 고친 문장을 대조한다 (FR-10). 장소명과 시간·요금·거리 수치만 본다 (UC-09 3단계)."""
    result = CheckResult(is_fact=looks_factual(text))
    mentioned = _mentioned_names(text, known_names)
    for _ in mentioned - confirmed_ids:
        result.warnings.append(Warning("unvisited_place", "이번 여행에서 확정되지 않은 장소가 나와요"))

    related = [pid for pid in (mentioned & confirmed_ids) | set(context_place_ids or []) if pid in facts]
    if not related:
        return result
    joined = " ".join(v for pid in related for v in facts[pid].values())

    def _labels(pid: str) -> str:
        return facts[pid].get("name", pid)

    t_text, t_src = time_tokens(text), time_tokens(joined)
    if t_text and not t_text <= t_src:
        src = ", ".join(facts[pid]["usetime"] for pid in related if facts[pid].get("usetime")) or "공식 운영시간 정보 없음"
        result.warnings.append(Warning("time_mismatch", f"공식 데이터의 시간과 달라요 (공식: {src})"))

    m_text, m_src = money_tokens(text), money_tokens(joined)
    if m_text and not m_text <= m_src:
        result.warnings.append(Warning("fee_mismatch", "공식 데이터의 요금과 달라요"))

    d_text, d_src = distance_tokens(text), distance_tokens(joined)
    if d_text and d_src and not d_text <= d_src:
        names = ", ".join(_labels(pid) for pid in related)
        result.warnings.append(Warning("distance_mismatch", f"공식 데이터의 거리·길이와 달라요 ({names})"))
    return result

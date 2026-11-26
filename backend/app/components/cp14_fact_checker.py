"""CP-14 Fact Checker (Domain 공용 모듈, 순수 로직).

책임: 여행기 문장의 장소 ID·필드 값을 공식 데이터와 대조한다 (FR-09, FR-10, AIR-06, UC-09).
- 생성 문장: 근거 장소가 확정 방문지인지, 사실 문장에 근거 필드가 있는지, 문장 속 숫자·시간이 근거 값에 있는지,
  한국어가 아닌 글자(한자·가나)가 섞였는지, '점심·저녁' 같은 시간대 표현이 사진 기록의 방문 시각과 맞는지 (D-07)
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
_DATE_RE = re.compile(r"(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_YEAR_RE = re.compile(r"(\d{4})\s*년")
_DAYNUM_RE = re.compile(r"(\d{1,2})\s*일\s*차|(\d{1,2})\s*박\s*(\d{1,2})\s*일")
# 한국어 여행기에 섞이면 안 되는 글자: 한자(CJK 통합·확장 A·호환), 히라가나·가타카나 (예: '午時가 되면', D-07)
_FOREIGN_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
# 방문 시각을 말하는 시간대 표현 → 해당하는 시(시작 이상, 끝 미만). 템플릿 문장(_time_phrase)이 쓰는 표현은 모두 이 범위 안에 든다
_TIME_OF_DAY = [("해 질 무렵", 16, 20), ("해질 무렵", 16, 20), ("해질녘", 16, 20), ("새벽", 0, 6), ("아침", 4, 11),
                ("오전", 4, 12), ("정오", 11, 14), ("점심", 11, 14), ("오후", 12, 19), ("저녁", 17, 24), ("밤", 19, 24)]
_HOUR_TOLERANCE = 1  # 촬영 시각 앞뒤 1시간까지 같은 시간대로 인정


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


def foreign_script(text: str) -> list[str]:
    """한국어 여행기에 섞인 한자·가나 글자 목록 (없으면 빈 목록)."""
    return _FOREIGN_RE.findall(text)


def _window(start, end) -> frozenset:
    """촬영 시각 범위 → 허용 시(앞뒤 _HOUR_TOLERANCE시간 포함)."""
    return frozenset(range(start.hour - _HOUR_TOLERANCE, end.hour + _HOUR_TOLERANCE + 1))


def time_of_day_words(text: str) -> list[tuple[str, int, int]]:
    """문장 속 시간대 표현과 그 시 범위. 긴 표현부터 찾고 찾은 부분은 지워 '해 질 무렵' 안의 다른 표현과 겹치지 않게 한다."""
    found, rest = [], text
    for word, a, b in _TIME_OF_DAY:
        if word in rest:
            if word == "밤" and re.search(r"밤(?:[가-힣]*나무|톨|송이|[을를이가]\s*(?:먹|줍|사))", rest):
                rest = rest.replace(word, " ")
                continue  # 먹는 밤(栗)은 시간대가 아님
            found.append((word, a, b))
            rest = rest.replace(word, " ")
    return found


@dataclass(frozen=True)
class TripRecord:
    """사진 촬영 정보로 확인되는 이번 여행의 방문 시각·날짜 (근거: 공식 데이터가 아니라 사용자 사진 기록).

    "10시에 감천문화마을로 향했다"처럼 방문 시각·날짜를 말하는 표현이 이 기록과 맞으면 공식 데이터 수치
    대조에서 뺀다. 기록과 다른 시각·날짜는 그대로 남아 대조 대상이 된다.
    """
    hours: frozenset = frozenset()  # 방문 시간대에 걸친 시(0~23). 끝 시각 다음 시까지 인정('10:40' → '11시쯤')
    dates: frozenset = frozenset()  # (연, 월, 일)
    days: int = 0
    place_hours: tuple = ()  # ((장소 ID, 허용 시 집합), …) — 시간대 표현 대조용 (D-07)
    day_hours: tuple = ()    # ((일차, 허용 시 집합), …) — 장소 언급 없는 문장의 시간대 표현 대조용

    @classmethod
    def from_spans(cls, spans) -> "TripRecord":
        hours: set[int] = set()
        dates: set[tuple[int, int, int]] = set()
        for start, end in spans:
            hours.update(range(start.hour, min(end.hour + 1, 23) + 1))
            dates.update({(start.year, start.month, start.day), (end.year, end.month, end.day)})
        return cls(frozenset(hours), frozenset(dates), len(dates))

    @classmethod
    def from_visits(cls, visits) -> "TripRecord":
        """visits: [(장소 ID 또는 None, 일차, 시작, 끝), …]"""
        base = cls.from_spans([(s, e) for _, _, s, e in visits])
        ph: dict[str, set[int]] = {}
        dh: dict[int, set[int]] = {}
        for pid, day, start, end in visits:
            w = _window(start, end)
            if pid:
                ph.setdefault(pid, set()).update(w)
            dh.setdefault(day, set()).update(w)
        return cls(base.hours, base.dates, base.days, tuple((k, frozenset(v)) for k, v in ph.items()),
                   tuple((k, frozenset(v)) for k, v in dh.items()))

    def visit_hours(self, place_ids, day: int | None) -> frozenset:
        """문장이 말하는 방문의 허용 시: 언급한 장소의 방문 시각, 없으면 그날 방문 시각 전체."""
        ph = dict(self.place_hours)
        got = frozenset().union(*(ph[p] for p in place_ids if p in ph)) if place_ids else frozenset()
        if got:
            return got
        dh = dict(self.day_hours)
        return dh.get(day, frozenset()) if day is not None else frozenset()


def strip_trip_record(text: str, trip: "TripRecord | None") -> str:
    """여행 기록과 맞는 날짜·일차·방문 시각 표현을 지운 문장 (대조용). 기록과 다른 표현은 그대로 둔다."""
    if trip is None:
        return text
    years = {y for y, _, _ in trip.dates}
    month_days = {(m, d) for _, m, d in trip.dates}

    def date_sub(mo: re.Match) -> str:
        ok = (int(mo.group(2)), int(mo.group(3))) in month_days and (mo.group(1) is None or int(mo.group(1)) in years)
        return " " if ok else mo.group(0)

    def day_sub(mo: re.Match) -> str:
        nums = [int(g) for g in mo.groups() if g]
        return " " if nums and max(nums) <= max(trip.days, 1) else mo.group(0)

    def kor_time_sub(mo: re.Match) -> str:
        ampm, h = mo.group(1), int(mo.group(2))
        hour = h + 12 if ampm in ("오후", "밤", "저녁") and h < 12 else h
        ok = hour in trip.hours or (not ampm and h < 12 and h + 12 in trip.hours)
        return " " if ok else mo.group(0)

    text = _DATE_RE.sub(date_sub, text)
    text = _YEAR_RE.sub(lambda mo: " " if int(mo.group(1)) in years else mo.group(0), text)
    text = _DAYNUM_RE.sub(day_sub, text)
    text = _TIME_RE.sub(lambda mo: " " if int(mo.group(1)) in trip.hours else mo.group(0), text)
    return _KOR_TIME_RE.sub(kor_time_sub, text)


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
    trip: TripRecord | None = None,
    day: int | None = None,
) -> CheckResult:
    """LLM이 만든 문장 하나를 대조한다.

    facts: {장소 ID: {필드: 값}} — LLM에 넣었던 확정 장소의 공식 데이터
    known_names: {장소 이름: 장소 ID} — 확정 장소와 후보로 조회됐던 장소 이름
    trip: 사진 기록의 방문 시각·날짜 — 이와 맞는 시각·날짜 표현은 수치 대조에서 뺀다
    """
    scan = strip_trip_record(text, trip)
    result = CheckResult(is_fact=declared_fact or looks_factual(scan))

    for pid in place_ids:
        if pid not in confirmed_ids:
            result.warnings.append(Warning("unconfirmed_place", "확정되지 않은 장소를 근거로 들었어요"))

    mentioned = _mentioned_names(text, known_names)
    for pid in mentioned - confirmed_ids:
        result.warnings.append(Warning("unvisited_place", "이번 여행에서 확정되지 않은 장소가 나와요"))

    odd = foreign_script(text)
    if odd:
        result.warnings.append(Warning("foreign_script", f"한국어가 아닌 글자가 섞여 있어요: {''.join(dict.fromkeys(odd))}"))

    # 시간대 표현 ↔ 사진 기록의 방문 시각 (운영시간 문장·공식 데이터에 이미 있는 표현은 제외)
    if trip is not None and "usetime" not in fields and not any(w in text for w in ("운영", "개장", "영업", "휴무", "입장")):
        refs = [p for p in dict.fromkeys(list(place_ids) + sorted(mentioned)) if p in confirmed_ids]
        allowed = trip.visit_hours(refs, day)
        src_text = " ".join(v for pid in refs for v in facts.get(pid, {}).values())
        for word, a, b in time_of_day_words(text):
            if allowed and word not in src_text and not (set(range(a, b)) & allowed):
                result.warnings.append(Warning("time_of_day_mismatch", f"사진 기록의 방문 시각과 맞지 않는 시간대 표현이에요: {word}"))

    if not result.is_fact:
        return result

    cited = [(pid, f) for pid in place_ids for f in fields if pid in facts]
    values = [facts[pid][f] for pid, f in cited if f in facts[pid]]
    if not values:
        result.warnings.append(Warning("no_source", "근거 데이터가 없는 사실 문장이에요"))
        return result

    joined = " ".join(values)
    if not number_tokens(scan) <= number_tokens(joined):
        missing = sorted(number_tokens(scan) - number_tokens(joined))
        result.warnings.append(Warning("number_mismatch", f"공식 데이터에 없는 수치가 있어요: {', '.join(missing)}"))
    return result


def check_edited_sentence(
    text: str,
    facts: dict[str, dict[str, str]],
    confirmed_ids: set[str],
    known_names: dict[str, str],
    context_place_ids: list[str] | None = None,
    trip: TripRecord | None = None,
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

    t_text, t_src = time_tokens(strip_trip_record(text, trip)), time_tokens(joined)
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
